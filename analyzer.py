#!/usr/bin/env python3
"""
analyzer.py — tree-sitter based C analyzer for Callgraph Studio

Replaces cflow + gawk pipeline.
Extracts:
  - Call graph (function → function calls)
  - Global variable deps (reads / writes per function)
  - Interrupt / ISR detection
  - RTOS task/queue/mutex/delay patterns (FreeRTOS + CMSIS-RTOS v2)
  - Hardware register access (peripheral->register)
  - Race condition candidates (ISR writers ∩ non-ISR readers)
  - Interrupt safety violations (globals written by ISR, read unprotected)
"""

import re, os
from pathlib import Path
from collections import defaultdict

try:
    import tree_sitter_c as tsc
    from tree_sitter import Language, Parser
    C_LANG = Language(tsc.language())
    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False

# ── Patterns ──────────────────────────────────────────────────────────────────

ISR_RE = re.compile(
    r'^(ISR_|irq_|IRQ_|EXTI\d+|TIM\d+_|USART\d+_|UART\d+_|SPI\d+_|I2C\d+_|'
    r'DMA\d+_|ADC\d*_|USB_|CAN\d*_|WWDG_|RTC_|NMI_|HardFault_|MemManage_|'
    r'BusFault_|UsageFault_|SVC_|DebugMon_|PendSV_|SysTick_|.*_IRQHandler|'
    r'.*_Handler|.*_ISR|.*_irq$|.*_isr$)',
    re.IGNORECASE
)

ENTRY_RE = re.compile(
    r'^(main|reset_handler|startup|_start|.*_init$|init_.*|setup)$',
    re.IGNORECASE
)

CRITICAL_SECTION_ENTER = {
    '__disable_irq', 'taskENTER_CRITICAL', 'taskENTER_CRITICAL_FROM_ISR',
    'portDISABLE_INTERRUPTS', '__set_PRIMASK', 'vPortEnterCritical',
    'osCriticalSectionEnter', 'NVIC_DisableIRQ', 'HAL_SuspendTick',
}
CRITICAL_SECTION_EXIT = {
    '__enable_irq', 'taskEXIT_CRITICAL', 'taskEXIT_CRITICAL_FROM_ISR',
    'portENABLE_INTERRUPTS', 'vPortExitCritical',
    'osCriticalSectionExit', 'NVIC_EnableIRQ', 'HAL_ResumeTick',
}

# FreeRTOS + CMSIS-RTOS v2 API → (kind, which_arg_is_target)
RTOS_API = {
    # Tasks
    'xTaskCreate':           ('task_create', 0),
    'xTaskCreateStatic':     ('task_create', 0),
    'xTaskCreateRestricted': ('task_create', 0),
    'osThreadNew':           ('task_create', 0),
    'vTaskDelete':           ('task_delete', 0),
    'osThreadTerminate':     ('task_delete', 0),
    'vTaskSuspend':          ('task_suspend',0),
    'vTaskResume':           ('task_resume', 0),
    # Queues
    'xQueueCreate':          ('queue_create', -1),
    'xQueueSend':            ('queue_send',   0),
    'xQueueSendToBack':      ('queue_send',   0),
    'xQueueSendToFront':     ('queue_send',   0),
    'xQueueSendFromISR':     ('queue_send',   0),
    'xQueueReceive':         ('queue_recv',   0),
    'xQueueReceiveFromISR':  ('queue_recv',   0),
    'xQueuePeek':            ('queue_peek',   0),
    'osMessageQueueNew':     ('queue_create', -1),
    'osMessageQueuePut':     ('queue_send',   0),
    'osMessageQueueGet':     ('queue_recv',   0),
    # Semaphores / Mutexes
    'xSemaphoreCreateMutex':       ('mutex_create', -1),
    'xSemaphoreCreateBinary':      ('sem_create',   -1),
    'xSemaphoreCreateCounting':    ('sem_create',   -1),
    'xSemaphoreTake':              ('mutex_take',   0),
    'xSemaphoreTakeFromISR':       ('mutex_take',   0),
    'xSemaphoreGive':              ('mutex_give',   0),
    'xSemaphoreGiveFromISR':       ('mutex_give',   0),
    'osMutexNew':                  ('mutex_create', -1),
    'osMutexAcquire':              ('mutex_take',   0),
    'osMutexRelease':              ('mutex_give',   0),
    'osSemaphoreNew':              ('sem_create',   -1),
    'osSemaphoreAcquire':          ('mutex_take',   0),
    'osSemaphoreRelease':          ('mutex_give',   0),
    # Delays
    'vTaskDelay':            ('delay', 0),
    'vTaskDelayUntil':       ('delay', 0),
    'osDelay':               ('delay', 0),
    'osDelayUntil':          ('delay', 0),
    'HAL_Delay':             ('delay', 0),
    # Event flags
    'xEventGroupSetBits':    ('event_set',  0),
    'xEventGroupWaitBits':   ('event_wait', 0),
    'osEventFlagsSet':       ('event_set',  0),
    'osEventFlagsWait':      ('event_wait', 0),
    # Notifications
    'xTaskNotify':           ('notify_send', 0),
    'xTaskNotifyWait':       ('notify_recv', -1),
    'xTaskNotifyFromISR':    ('notify_send', 0),
}

# Known peripheral base names (STM32-centric, extensible)
PERIPHERAL_RE = re.compile(
    r'^(GPIOA|GPIOB|GPIOC|GPIOD|GPIOE|GPIOF|GPIOG|GPIOH|GPIOI|GPIOJ|GPIOK|'
    r'TIM\d+|USART\d+|UART\d+|SPI\d+|I2C\d+|ADC\d+|DAC\d*|DMA\d+|'
    r'RCC|FLASH|PWR|SYSCFG|EXTI|NVIC|SCB|SysTick|CAN\d*|USB|RTC|IWDG|WWDG|'
    r'SDIO|FSMC|FMC|ETH|DCMI|CRYP|HASH|RNG|LTDC|SAI\d*|DFSDM\d*|QUADSPI)$'
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _text(node):
    return node.text.decode('utf-8', 'replace') if node else ''

def _get_args(call_node):
    """Return list of argument text strings for a call_expression node."""
    args_node = call_node.child_by_field_name('arguments')
    if not args_node:
        return []
    return [_text(c).strip()
            for c in args_node.children
            if c.type not in (',', '(', ')', ';')]

def _declarator_name(node):
    """Recursively extract the identifier from any declarator node."""
    if node is None:
        return None
    if node.type == 'identifier':
        return _text(node)
    for c in node.children:
        r = _declarator_name(c)
        if r:
            return r
    return None

def _fn_name_from_def(func_def_node):
    """Extract function name from a function_definition node."""
    decl = func_def_node.child_by_field_name('declarator')
    if not decl:
        return None
    # declarator can be: pointer_declarator → function_declarator → identifier
    # or directly function_declarator → identifier
    def find_fn_decl(n):
        if n.type == 'function_declarator':
            inner = n.child_by_field_name('declarator')
            return _declarator_name(inner) if inner else None
        for c in n.children:
            r = find_fn_decl(c)
            if r:
                return r
        return None
    return find_fn_decl(decl)


# ── Per-file analysis ─────────────────────────────────────────────────────────

def analyze_file(filepath, global_vars):
    """
    Parse one .c file with tree-sitter.
    Returns:
        functions : dict  fn_name → {file, line, calls, reads, writes,
                                     rtos, peripherals, is_isr, has_critical,
                                     delays_in_loop}
        file_globals : dict  name → {file, line, volatile, is_extern}
    """
    try:
        src = Path(filepath).read_bytes()
    except Exception:
        return {}, {}

    parser = Parser(C_LANG)
    tree   = parser.parse(src)
    root   = tree.root_node

    # ── 1. Collect file-scope globals ─────────────────────────────────────
    file_globals = {}
    for child in root.children:
        if child.type != 'declaration':
            continue
        qualifiers = {_text(c) for c in child.children
                      if c.type in ('type_qualifier', 'storage_class_specifier')}
        is_extern  = 'extern' in qualifiers
        is_volatile= 'volatile' in qualifiers
        is_static  = 'static' in qualifiers
        # Find all declarators in this declaration
        for c in child.children:
            if c.type in ('init_declarator', 'identifier', 'pointer_declarator',
                          'array_declarator'):
                name = _declarator_name(c)
                if name:
                    file_globals[name] = {
                        'file':     filepath,
                        'line':     child.start_point[0] + 1,
                        'volatile': is_volatile,
                        'extern':   is_extern,
                        'static':   is_static,
                    }

    # All knowable globals for this file = file_globals + passed-in project globals
    all_globals = set(global_vars) | set(file_globals)

    # ── 2. Analyze each function ───────────────────────────────────────────
    functions = {}

    def analyze_body(body_node, fn_name):
        calls        = []
        reads        = set()
        writes       = set()
        rtos_calls   = []
        peripherals  = set()   # "GPIOA->ODR" style
        critical_depth = [0]   # mutable counter via list
        has_critical = [False]
        delay_in_loop= [False]
        in_loop      = [0]

        def walk(node, lhs=False, loop_depth=0):
            t = node.type

            # ── Loop tracking ──────────────────────────────────────────
            if t in ('for_statement', 'while_statement', 'do_statement'):
                in_loop[0] += 1
                for c in node.children:
                    walk(c, loop_depth=in_loop[0])
                in_loop[0] -= 1
                return

            # ── Call expression ────────────────────────────────────────
            if t == 'call_expression':
                fn_node = node.child_by_field_name('function')
                fn_text = _text(fn_node) if fn_node else ''

                # Strip potential cast / dereference for simple cases
                if fn_node and fn_node.type == 'identifier':
                    callee = fn_text

                    # Critical section tracking
                    if callee in CRITICAL_SECTION_ENTER:
                        critical_depth[0] += 1
                        has_critical[0] = True
                    elif callee in CRITICAL_SECTION_EXIT:
                        critical_depth[0] = max(0, critical_depth[0] - 1)

                    # RTOS API
                    if callee in RTOS_API:
                        kind, arg_idx = RTOS_API[callee]
                        args = _get_args(node)
                        target = args[arg_idx] if 0 <= arg_idx < len(args) else None
                        rtos_calls.append({
                            'api':    callee,
                            'kind':   kind,
                            'target': target,
                            'line':   node.start_point[0] + 1,
                            'in_critical': critical_depth[0] > 0,
                        })
                        if kind == 'delay' and in_loop[0] > 0:
                            delay_in_loop[0] = True
                    else:
                        calls.append(callee)

                # Walk arguments
                args_node = node.child_by_field_name('arguments')
                if args_node:
                    for c in args_node.children:
                        walk(c, lhs=False, loop_depth=loop_depth)
                return

            # ── Assignment ────────────────────────────────────────────
            if t == 'assignment_expression':
                l = node.child_by_field_name('left')
                r = node.child_by_field_name('right')
                if l: walk(l, lhs=True,  loop_depth=loop_depth)
                if r: walk(r, lhs=False, loop_depth=loop_depth)
                return

            # ── Compound assignment / update (+=, |=, ++, etc.) ───────
            if t in ('update_expression', 'compound_assignment_expr',
                     'augmented_assignment_expression'):
                # The operand is both read and written
                for c in node.children:
                    if c.type not in ('++','--','+=','-=','|=','&=',
                                      '^=','<<=','>>=','*=','/=','%=','='):
                        walk(c, lhs=True, loop_depth=loop_depth)
                return

            # ── Field access: PERIPH->REG ─────────────────────────────
            if t == 'field_expression':
                base  = node.child_by_field_name('argument')
                field = node.child_by_field_name('field')
                if base and field:
                    base_text  = _text(base)
                    field_text = _text(field)
                    if PERIPHERAL_RE.match(base_text):
                        key = f"{base_text}->{field_text}"
                        peripherals.add(key)
                        if lhs: writes.add(key)
                        else:   reads.add(key)
                        return
                # Fall through for struct member access on non-peripherals
                for c in node.children: walk(c, lhs, loop_depth)
                return

            # ── Identifier ────────────────────────────────────────────
            if t == 'identifier':
                name = _text(node)
                if name in all_globals:
                    if lhs: writes.add(name)
                    else:   reads.add(name)
                return

            # ── Default: recurse ──────────────────────────────────────
            for c in node.children:
                walk(c, lhs=lhs, loop_depth=loop_depth)

        walk(body_node)

        # Deduplicate calls, preserve order
        seen = set()
        unique_calls = []
        for c in calls:
            if c not in seen:
                seen.add(c)
                unique_calls.append(c)

        return {
            'calls':        unique_calls,
            'reads':        sorted(reads  - writes),   # pure reads
            'writes':       sorted(writes),
            'rw':           sorted(reads & writes),    # read-modify-write
            'rtos':         rtos_calls,
            'peripherals':  sorted(peripherals),
            'has_critical': has_critical[0],
            'delay_in_loop':delay_in_loop[0],
        }

    for child in root.children:
        if child.type != 'function_definition':
            continue
        fn_name = _fn_name_from_def(child)
        if not fn_name:
            continue
        body = child.child_by_field_name('body')
        if not body:
            continue

        result = analyze_body(body, fn_name)
        functions[fn_name] = {
            'file':         filepath,
            'line':         child.start_point[0] + 1,
            'is_isr':       bool(ISR_RE.match(fn_name)),
            'is_entry':     bool(ENTRY_RE.match(fn_name)),
            **result,
        }

    return functions, file_globals


# ── Project-level analysis ────────────────────────────────────────────────────

def analyze_project(source_files, src_root, push_fn=None):
    """
    Analyze all C files in source_files.
    push_fn: callback(str) for progress messages (SSE).
    Returns complete graph dict compatible with existing frontend.
    """
    def push(msg):
        if push_fn:
            push_fn(msg)

    if not TS_AVAILABLE:
        push("[error] tree-sitter not available — install: pip install tree-sitter tree-sitter-c")
        return None

    push(f"[info] tree-sitter: analyzing {len(source_files)} files...")

    # ── Pass 1: collect all file-scope globals across project ─────────────
    push("[info] Pass 1: collecting globals...")
    all_file_globals = {}   # name → meta (last definition wins)
    for fpath in source_files:
        try:
            src = Path(fpath).read_bytes()
        except Exception:
            continue
        parser = Parser(C_LANG)
        tree   = parser.parse(src)
        root   = tree.root_node
        for child in root.children:
            if child.type != 'declaration':
                continue
            qualifiers = {_text(c) for c in child.children
                          if c.type in ('type_qualifier','storage_class_specifier')}
            is_volatile = 'volatile' in qualifiers
            is_extern   = 'extern'   in qualifiers
            is_static   = 'static'   in qualifiers
            for c in child.children:
                if c.type in ('init_declarator','identifier','pointer_declarator',
                              'array_declarator'):
                    name = _declarator_name(c)
                    if name and name not in ('NULL','true','false'):
                        rel = str(Path(fpath).relative_to(src_root))
                        all_file_globals[name] = {
                            'file':     rel,
                            'line':     child.start_point[0] + 1,
                            'volatile': is_volatile,
                            'extern':   is_extern,
                            'static':   is_static,
                        }

    push(f"[info] Found {len(all_file_globals)} global variables")

    # ── Pass 2: analyze each file ─────────────────────────────────────────
    push("[info] Pass 2: analyzing functions...")
    all_functions = {}   # fn_name → enriched dict

    for fpath in source_files:
        fns, _ = analyze_file(fpath, set(all_file_globals.keys()))
        for fn_name, data in fns.items():
            rel = str(Path(fpath).relative_to(src_root))
            segs = rel.split('/')
            mod  = segs[0] if len(segs) >= 2 else '.'
            data['file'] = rel
            data['mod']  = mod
            all_functions[fn_name] = data

    push(f"[info] Found {len(all_functions)} functions")

    # ── Pass 3: build call graph ──────────────────────────────────────────
    push("[info] Pass 3: building call graph...")
    proj_fns = set(all_functions.keys())
    edges   = defaultdict(list)   # caller → [callee, ...]
    callers = defaultdict(list)   # callee → [caller, ...]

    for fn_name, data in all_functions.items():
        for callee in data['calls']:
            if callee not in edges[fn_name]:
                edges[fn_name].append(callee)
            if fn_name not in callers[callee]:
                callers[callee].append(fn_name)

    # ── Pass 4: global variable dependency graph ──────────────────────────
    push("[info] Pass 4: global variable dependencies...")

    # var → {writers: [fn,...], readers: [fn,...], rw: [fn,...]}
    var_deps = defaultdict(lambda: {'writers':[], 'readers':[], 'rw':[]})

    for fn_name, data in all_functions.items():
        for v in data.get('writes', []):
            if v in all_file_globals and fn_name not in var_deps[v]['writers']:
                var_deps[v]['writers'].append(fn_name)
        for v in data.get('reads', []):
            if v in all_file_globals and fn_name not in var_deps[v]['readers']:
                var_deps[v]['readers'].append(fn_name)
        for v in data.get('rw', []):
            if v in all_file_globals and fn_name not in var_deps[v]['rw']:
                var_deps[v]['rw'].append(fn_name)

    # ── Pass 5: race condition / interrupt safety analysis ────────────────
    push("[info] Pass 5: interrupt safety analysis...")
    races = []

    isr_fns  = {fn for fn, d in all_functions.items() if d.get('is_isr')}
    task_fns = {fn for fn, d in all_functions.items() if not d.get('is_isr')}

    for var, deps in var_deps.items():
        meta = all_file_globals.get(var, {})
        isr_writers  = [f for f in deps['writers'] if f in isr_fns]
        isr_rw       = [f for f in deps['rw']      if f in isr_fns]
        task_readers = [f for f in deps['readers'] + deps['rw'] if f in task_fns]
        task_writers = [f for f in deps['writers'] + deps['rw'] if f in task_fns]

        all_isr_writers = isr_writers + isr_rw
        if not all_isr_writers:
            continue

        for task_fn in task_readers + task_writers:
            fn_data = all_functions.get(task_fn, {})
            protected = fn_data.get('has_critical', False)
            access = 'write' if task_fn in task_writers else 'read'
            severity = 'high' if meta.get('volatile') else 'medium'
            if protected:
                severity = 'low'

            races.append({
                'var':          var,
                'isr_writers':  all_isr_writers,
                'task_fn':      task_fn,
                'task_access':  access,
                'protected':    protected,
                'volatile':     meta.get('volatile', False),
                'severity':     severity,
                'file':         meta.get('file', ''),
            })

    # Deduplicate
    seen_races = set()
    unique_races = []
    for r in races:
        key = (r['var'], r['task_fn'])
        if key not in seen_races:
            seen_races.add(key)
            unique_races.append(r)

    unique_races.sort(key=lambda r: ('high','medium','low').index(r['severity']))
    push(f"[info] Race candidates: {len(unique_races)} ({sum(1 for r in unique_races if r['severity']=='high')} high severity)")

    # ── Pass 6: RTOS graph ────────────────────────────────────────────────
    push("[info] Pass 6: RTOS architecture...")
    rtos_tasks   = {}   # task_fn → {creates, sends_to, recvs_from, takes, gives}
    rtos_objects = defaultdict(lambda: {'kind':'unknown','users':[]})  # queue/mutex name → meta

    for fn_name, data in all_functions.items():
        for rc in data.get('rtos', []):
            kind   = rc['kind']
            target = rc['target']
            if not target:
                continue

            # Clean target: strip &, quotes, type casts, struct access
            target = re.sub(r'^&', '', target).strip()
            target = re.sub(r'^"(.*)"$', r'\1', target)
            target = re.sub(r'^\(.*?\)', '', target).strip()
            # Skip struct field access (e.g. thread_def->pthread), NULL, numeric literals
            if not target or '->' in target or '.' in target or target == 'NULL' or target.isdigit():
                continue

            # Skip FreeRTOS/CMSIS internal functions
            RTOS_INTERNAL = {'prvIdleTask','prvTimerTask','prvCheckTasksWaitingTermination',
                             'configIDLE_TASK_NAME','idle','timer','IDLE'}
            if kind == 'task_create':
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                if target and target not in rtos_tasks[fn_name]['creates']:
                    rtos_tasks[fn_name]['creates'].append(target)
                # Only add target as a task node if it's a project function (not RTOS internal)
                if target and target not in RTOS_INTERNAL and not target.startswith('prv'):
                    if target not in rtos_tasks:
                        rtos_tasks[target] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}

            elif kind == 'queue_send':
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                rtos_tasks[fn_name]['sends_to'].append(target)
                rtos_objects[target]['kind'] = 'queue'
                if fn_name not in rtos_objects[target]['users']:
                    rtos_objects[target]['users'].append(fn_name)

            elif kind == 'queue_recv':
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                rtos_tasks[fn_name]['recvs_from'].append(target)
                rtos_objects[target]['kind'] = 'queue'
                if fn_name not in rtos_objects[target]['users']:
                    rtos_objects[target]['users'].append(fn_name)

            elif kind in ('mutex_take', 'mutex_create', 'sem_create'):
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                rtos_tasks[fn_name]['takes'].append(target)
                rtos_objects[target]['kind'] = 'mutex' if 'mutex' in kind else 'semaphore'
                if fn_name not in rtos_objects[target]['users']:
                    rtos_objects[target]['users'].append(fn_name)

            elif kind == 'mutex_give':
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                rtos_tasks[fn_name]['gives'].append(target)

            elif kind == 'delay':
                if fn_name not in rtos_tasks:
                    rtos_tasks[fn_name] = {'creates':[],'sends_to':[],'recvs_from':[],'takes':[],'gives':[],'delays':[]}
                rtos_tasks[fn_name]['delays'].append(rc.get('target',''))

    # ── Pass 7: peripheral register map ───────────────────────────────────
    push("[info] Pass 7: peripheral register map...")
    periph_map = defaultdict(lambda: {'readers':[], 'writers':[], 'rw':[]})

    for fn_name, data in all_functions.items():
        for p in data.get('peripherals', []):
            base = p.split('->')[0]
            for access_list, store in [
                (data.get('writes',[]), 'writers'),
                (data.get('reads', []), 'readers'),
                (data.get('rw',   []), 'rw'),
            ]:
                if p in access_list:
                    if fn_name not in periph_map[base][store]:
                        periph_map[base][store].append(fn_name)

    # ── Pass 8: build node list ───────────────────────────────────────────
    all_fn_names = set(all_functions.keys()) | {c for cs in edges.values() for c in cs}
    nodes = []
    for fn in sorted(all_fn_names):
        data = all_functions.get(fn, {})
        nodes.append({
            'id':           fn,
            'file':         data.get('file', ''),
            'mod':          data.get('mod', 'external'),
            'line':         data.get('line', 0),
            'type':         'project' if fn in proj_fns else 'external',
            'is_isr':       data.get('is_isr', False),
            'is_entry':     data.get('is_entry', False),
            'has_critical': data.get('has_critical', False),
            'delay_in_loop':data.get('delay_in_loop', False),
            'out_degree':   len(edges.get(fn, [])),
            'in_degree':    len(callers.get(fn, [])),
            'reads':        data.get('reads', []),
            'writes':       data.get('writes', []),
            'rw':           data.get('rw', []),
            'peripherals':  data.get('peripherals', []),
            'rtos':         data.get('rtos', []),
        })

    # Module edges
    mod_edges = defaultdict(int)
    for caller_fn, callees in edges.items():
        cm = all_functions.get(caller_fn, {}).get('mod', 'external')
        for callee_fn in callees:
            em = all_functions.get(callee_fn, {}).get('mod', 'external')
            if cm != em:
                mod_edges[f"{cm}→{em}"] += 1

    total_edges = sum(len(v) for v in edges.values())
    push(f"[ok] Graph: {len(nodes)} nodes, {total_edges} edges, "
         f"{len(var_deps)} globals tracked, {len(unique_races)} race candidates")

    return {
        'source':     str(src_root),
        'files':      len(source_files),
        'nodes':      nodes,
        'edges':      dict(edges),
        'callers':    dict(callers),
        'mod_edges':  dict(mod_edges),
        'mods':       sorted(set(n['mod'] for n in nodes)),
        # New fields
        'globals':    {k: {**v, 'readers': var_deps[k]['readers'],
                                'writers': var_deps[k]['writers'],
                                'rw':      var_deps[k]['rw']}
                       for k, v in all_file_globals.items()},
        'races':      unique_races,
        'rtos':       {'tasks': rtos_tasks, 'objects': dict(rtos_objects)},
        'peripherals':dict(periph_map),
    }
