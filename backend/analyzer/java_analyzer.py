import math
import javalang
from javalang.tree import (
    ClassDeclaration,
    InterfaceDeclaration,
    EnumDeclaration,
    MethodDeclaration,
    ConstructorDeclaration,
    FieldDeclaration,
    IfStatement,
    ForStatement,
    WhileStatement,
    DoStatement,
    CatchClause,
    TernaryExpression,
    SwitchStatement,
    SwitchStatementCase,
    BinaryOperation,
    TryStatement,
    SynchronizedStatement,
    ReferenceType,
    ClassCreator,
)

STANDARD_JAVA_TYPES = {
    "String",
    "Object",
    "Integer",
    "Long",
    "Double",
    "Float",
    "Boolean",
    "Byte",
    "Short",
    "Character",
    "Void",
    "Math",
    "System",
    "List",
    "ArrayList",
    "Map",
    "HashMap",
    "Set",
    "HashSet",
    "Collection",
    "Collections",
    "Optional",
    "Stream",
    "Exception",
    "RuntimeException",
    "IllegalArgumentException",
    "IllegalStateException",
    "NullPointerException",
    "Override",
    "Deprecated",
    "SuppressWarnings",
}

NESTING_NODE_TYPES = (
    IfStatement,
    ForStatement,
    WhileStatement,
    DoStatement,
    SwitchStatement,
    TryStatement,
    SynchronizedStatement,
)


def count_lines_and_comments(source: str) -> dict:
    """
    Accurately count total lines, physical code lines (LOC), comment lines,
    and blank lines in a Java source string, handling single-line and multi-line comments.
    """
    lines = source.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return {
            "total_lines": 0,
            "loc": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "comment_ratio": 0.0,
        }

    blank_lines = 0
    comment_lines = 0
    loc = 0
    in_block_comment = False

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if in_block_comment:
                comment_lines += 1
            else:
                blank_lines += 1
            continue

        has_code = False
        has_comment = in_block_comment
        i = 0
        n = len(stripped)
        in_string = False
        in_char = False

        while i < n:
            ch = stripped[i]
            nxt = stripped[i + 1] if i + 1 < n else ""

            if in_block_comment:
                has_comment = True
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_string:
                has_code = True
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == '"':
                    in_string = False
                i += 1
                continue

            if in_char:
                has_code = True
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == "'":
                    in_char = False
                i += 1
                continue

            # Not in comment or literal
            if ch == "/" and nxt == "/":
                has_comment = True
                break
            if ch == "/" and nxt == "*":
                has_comment = True
                in_block_comment = True
                i += 2
                continue
            if ch == '"':
                in_string = True
                has_code = True
                i += 1
                continue
            if ch == "'":
                in_char = True
                has_code = True
                i += 1
                continue
            if not ch.isspace():
                has_code = True
            i += 1

        if has_code:
            loc += 1
        if has_comment and not has_code:
            comment_lines += 1
        elif has_comment and has_code:
            # Inline comment on a code line counts toward comment presence as well
            comment_lines += 1

    non_blank = max(loc + comment_lines, 1)
    comment_ratio = min(100.0, (comment_lines / max(total_lines - blank_lines, 1)) * 100.0)
    return {
        "total_lines": total_lines,
        "loc": loc,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "comment_ratio": round(comment_ratio, 2),
    }


def compute_halstead_volume(source: str) -> float:
    """
    Compute Halstead Volume (V) from Java lexical tokens using javalang.tokenizer.
    V = N * log2(n), where N = total operators + operands, n = distinct operators + operands.
    """
    try:
        tokens = list(javalang.tokenizer.tokenize(source))
    except Exception:
        return 0.0

    if not tokens:
        return 0.0

    operators = []
    operands = []
    for tok in tokens:
        cls_name = tok.__class__.__name__
        if cls_name in ("Operator", "Separator", "Keyword", "Modifier", "BasicType"):
            operators.append(tok.value)
        else:
            operands.append(tok.value)

    n1 = len(set(operators))
    n2 = len(set(operands))
    N1 = len(operators)
    N2 = len(operands)

    vocabulary = n1 + n2
    length = N1 + N2
    if vocabulary <= 1 or length == 0:
        return 1.0
    volume = length * math.log2(vocabulary)
    return round(volume, 2)


def compute_method_complexity(method_node) -> int:
    """
    Compute AST-based McCabe Cyclomatic Complexity for a single MethodDeclaration or ConstructorDeclaration.
    Base complexity = 1
    +1 for each IfStatement, ForStatement, WhileStatement, DoStatement, CatchClause, TernaryExpression
    +1 for each case label in SwitchStatementCase
    +1 for each short-circuit boolean operator (&&, ||) in BinaryOperation
    """
    complexity = 1
    for _, node in method_node:
        if isinstance(
            node,
            (
                IfStatement,
                ForStatement,
                WhileStatement,
                DoStatement,
                CatchClause,
                TernaryExpression,
            ),
        ):
            complexity += 1
        elif isinstance(node, SwitchStatementCase):
            case_count = len(node.case) if node.case else 1
            complexity += max(1, case_count)
        elif isinstance(node, BinaryOperation) and node.operator in ("&&", "||"):
            complexity += 1
    return complexity


def compute_max_nesting_depth(node, current_depth: int = 0) -> int:
    """
    Recursively traverse AST children of a method/constructor to compute maximum control-structure nesting depth.
    """
    max_d = current_depth
    if not hasattr(node, "children"):
        return max_d

    for child in node.children:
        if child is None:
            continue
        items = child if isinstance(child, (list, tuple)) else [child]
        for item in items:
            if hasattr(item, "children"):
                is_else_if = isinstance(node, IfStatement) and item is getattr(
                    node, "false_statement", None
                ) and isinstance(item, IfStatement)
                if isinstance(item, NESTING_NODE_TYPES) and not is_else_if:
                    child_d = compute_max_nesting_depth(item, current_depth + 1)
                else:
                    child_d = compute_max_nesting_depth(item, current_depth)
                if child_d > max_d:
                    max_d = child_d
    return max_d


def estimate_method_loc(source_lines: list[str], start_line_1based: int) -> int:
    """
    Determine the line span of a method or constructor starting at start_line_1based
    by matching opening and closing braces outside string/comment blocks.
    """
    if not source_lines or start_line_1based <= 0 or start_line_1based > len(source_lines):
        return 1

    idx = start_line_1based - 1
    brace_depth = 0
    found_open_brace = False
    in_block_comment = False

    for line_idx in range(idx, len(source_lines)):
        line = source_lines[line_idx]
        i = 0
        n = len(line)
        in_str = False
        in_chr = False

        while i < n:
            ch = line[i]
            nxt = line[i + 1] if i + 1 < n else ""

            if in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
                i += 1
                continue

            if in_chr:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == "'":
                    in_chr = False
                i += 1
                continue

            if ch == "/" and nxt == "/":
                break
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue
            if ch == '"':
                in_str = True
                i += 1
                continue
            if ch == "'":
                in_chr = True
                i += 1
                continue

            if ch == "{":
                brace_depth += 1
                found_open_brace = True
            elif ch == "}":
                brace_depth -= 1
                if found_open_brace and brace_depth <= 0:
                    return max(1, (line_idx - idx) + 1)
            elif ch == ";" and not found_open_brace:
                # Abstract or interface method declaration without body
                return max(1, (line_idx - idx) + 1)
            i += 1

    return max(1, len(source_lines) - idx)


def compute_maintainability_index(
    halstead_volume: float, cyclomatic_complexity: int, loc: int, comment_ratio_pct: float
) -> float:
    """
    Compute the normalized 0-100 Maintainability Index (SEI / Visual Studio derivative):
    MI_raw = 171 - 5.2 * ln(max(V, 1)) - 0.23 * G - 16.2 * ln(max(LOC, 1)) + 50 * sin(sqrt(2.4 * CM))
    where CM is comment ratio in [0, 1].
    Normalized to [0, 100]: max(0, min(100, MI_raw * 100 / 171))
    """
    v = max(float(halstead_volume), 1.0)
    g = max(int(cyclomatic_complexity), 1)
    l = max(int(loc), 1)
    cm = max(0.0, min(1.0, float(comment_ratio_pct) / 100.0))

    mi_raw = (
        171.0
        - 5.2 * math.log(v)
        - 0.23 * g
        - 16.2 * math.log(l)
        + 50.0 * math.sin(math.sqrt(2.4 * cm))
    )
    mi_norm = max(0.0, min(100.0, (mi_raw * 100.0) / 171.0))
    return round(mi_norm, 2)


def detect_code_smells(metrics: dict, thresholds: dict) -> list[dict]:
    """
    Evaluate deterministic static code-smell rules against extracted file and method metrics.
    """
    smells = []
    god_loc = thresholds.get("god_class_loc", 250)
    god_methods = thresholds.get("god_class_methods", 15)
    long_m_loc = thresholds.get("long_method_loc", 40)
    high_m_cc = thresholds.get("high_method_complexity", 10)
    high_f_cc = thresholds.get("high_file_complexity", 25)
    max_params_t = thresholds.get("max_parameters_threshold", 5)
    deep_nest_t = thresholds.get("deep_nesting_threshold", 4)
    min_comment_t = thresholds.get("min_comment_ratio_pct", 8.0)
    high_fanout_t = thresholds.get("high_fan_out_threshold", 12)

    # 1. God Class / Large Class
    if metrics["loc"] >= god_loc or metrics["method_count"] >= god_methods:
        smells.append(
            {
                "type": "GOD_CLASS",
                "label": "God Class / Large Class",
                "severity": "HIGH",
                "metric_value": f"{metrics['loc']} LOC, {metrics['method_count']} methods",
                "threshold": f"{god_loc} LOC or {god_methods} methods",
                "message": (
                    f"File has {metrics['loc']} LOC and {metrics['method_count']} methods, "
                    f"exceeding single-responsibility size thresholds ({god_loc} LOC / {god_methods} methods)."
                ),
            }
        )

    # 2. High File Cyclomatic Complexity
    if metrics["cyclomatic_complexity"] >= high_f_cc:
        smells.append(
            {
                "type": "HIGH_FILE_COMPLEXITY",
                "label": "High File Cyclomatic Complexity",
                "severity": "HIGH" if metrics["cyclomatic_complexity"] >= high_f_cc * 1.5 else "MEDIUM",
                "metric_value": metrics["cyclomatic_complexity"],
                "threshold": high_f_cc,
                "message": (
                    f"Aggregate file cyclomatic complexity is {metrics['cyclomatic_complexity']} "
                    f"(threshold: {high_f_cc}), increasing test path combinations."
                ),
            }
        )

    # 3. High Method Complexity
    complex_methods = [
        m for m in metrics.get("methods_detail", []) if m["complexity"] >= high_m_cc
    ]
    if complex_methods:
        names = ", ".join(f"{m['name']} (CC={m['complexity']})" for m in complex_methods[:3])
        smells.append(
            {
                "type": "COMPLEX_METHOD",
                "label": "High Method Cyclomatic Complexity",
                "severity": "HIGH" if metrics["max_method_complexity"] >= high_m_cc + 5 else "MEDIUM",
                "metric_value": metrics["max_method_complexity"],
                "threshold": high_m_cc,
                "message": (
                    f"{len(complex_methods)} method(s) exceed complexity threshold of {high_m_cc}: {names}."
                ),
            }
        )

    # 4. Long Method
    long_methods = [
        m for m in metrics.get("methods_detail", []) if m["loc"] >= long_m_loc
    ]
    if long_methods:
        names = ", ".join(f"{m['name']} ({m['loc']} lines)" for m in long_methods[:3])
        smells.append(
            {
                "type": "LONG_METHOD",
                "label": "Long Method",
                "severity": "MEDIUM",
                "metric_value": metrics["max_method_loc"],
                "threshold": long_m_loc,
                "message": (
                    f"{len(long_methods)} method(s) exceed {long_m_loc} lines: {names}."
                ),
            }
        )

    # 5. Deep Control-Flow Nesting
    if metrics["max_nesting_depth"] > deep_nest_t:
        smells.append(
            {
                "type": "DEEP_NESTING",
                "label": "Deep Control-Flow Nesting",
                "severity": "HIGH" if metrics["max_nesting_depth"] >= deep_nest_t + 2 else "MEDIUM",
                "metric_value": metrics["max_nesting_depth"],
                "threshold": deep_nest_t,
                "message": (
                    f"Maximum control-structure nesting depth is {metrics['max_nesting_depth']} "
                    f"(threshold: {deep_nest_t}), reducing readability."
                ),
            }
        )

    # 6. Excessive Parameter List
    if metrics["max_parameters"] > max_params_t:
        smells.append(
            {
                "type": "LONG_PARAMETER_LIST",
                "label": "Excessive Parameter List",
                "severity": "LOW",
                "metric_value": metrics["max_parameters"],
                "threshold": max_params_t,
                "message": (
                    f"Method signature contains {metrics['max_parameters']} parameters "
                    f"(threshold: {max_params_t}). Consider introducing a Parameter Object."
                ),
            }
        )

    # 7. High Coupling / Fan-Out
    if metrics["fan_out"] >= high_fanout_t:
        smells.append(
            {
                "type": "HIGH_COUPLING",
                "label": "High Eff-Coupling (Fan-Out)",
                "severity": "MEDIUM",
                "metric_value": metrics["fan_out"],
                "threshold": high_fanout_t,
                "message": (
                    f"File references {metrics['fan_out']} distinct external types "
                    f"(threshold: {high_fanout_t}), indicating tight coupling."
                ),
            }
        )

    # 8. Low Comment / Documentation Density
    if metrics["loc"] >= 30 and metrics["comment_ratio"] < min_comment_t:
        smells.append(
            {
                "type": "LOW_DOCUMENTATION",
                "label": "Low Documentation / Comment Ratio",
                "severity": "LOW",
                "metric_value": f"{metrics['comment_ratio']:.1f}%",
                "threshold": f"{min_comment_t:.1f}%",
                "message": (
                    f"Comment density is {metrics['comment_ratio']:.1f}% across {metrics['loc']} LOC "
                    f"(minimum recommended heuristic: {min_comment_t:.1f}%)."
                ),
            }
        )

    return smells


def analyze_java_file(
    abs_path: str, rel_path: str, file_name: str, thresholds: dict = None
) -> dict:
    """
    Analyze a single Java source file and extract AST-based software engineering metrics.
    Handles syntax errors or malformed files gracefully without raising unhandled exceptions.
    """
    thresholds = thresholds or {}
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception as exc:
        return {
            "file_name": file_name,
            "file_path": rel_path,
            "package_name": None,
            "parse_status": "PARSE_ERROR",
            "parse_error": f"File read error: {str(exc)}",
            "total_lines": 0,
            "loc": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "comment_ratio": 0.0,
            "class_count": 0,
            "interface_count": 0,
            "method_count": 0,
            "field_count": 0,
            "cyclomatic_complexity": 0,
            "avg_method_complexity": 0.0,
            "max_method_complexity": 0,
            "max_nesting_depth": 0,
            "import_count": 0,
            "fan_out": 0,
            "coupling_score": 0.0,
            "long_method_count": 0,
            "max_method_loc": 0,
            "max_parameters": 0,
            "maintainability_index": None,
            "halstead_volume": None,
            "code_smell_count": 0,
            "code_smells": [],
            "methods_detail": [],
        }

    line_stats = count_lines_and_comments(source)
    source_lines = source.splitlines()

    try:
        tree = javalang.parse.parse(source)
    except javalang.parser.JavaSyntaxError as syn_err:
        err_desc = getattr(syn_err, "description", str(syn_err))
        at_pos = getattr(syn_err, "at", None)
        pos_str = f" at token '{at_pos.value}' (line {at_pos.position.line})" if (at_pos and getattr(at_pos, "position", None)) else ""
        return {
            "file_name": file_name,
            "file_path": rel_path,
            "package_name": None,
            "parse_status": "PARSE_ERROR",
            "parse_error": f"Java syntax error: {err_desc}{pos_str}",
            **line_stats,
            "class_count": 0,
            "interface_count": 0,
            "method_count": 0,
            "field_count": 0,
            "cyclomatic_complexity": 0,
            "avg_method_complexity": 0.0,
            "max_method_complexity": 0,
            "max_nesting_depth": 0,
            "import_count": 0,
            "fan_out": 0,
            "coupling_score": 0.0,
            "long_method_count": 0,
            "max_method_loc": 0,
            "max_parameters": 0,
            "maintainability_index": None,
            "halstead_volume": None,
            "code_smell_count": 0,
            "code_smells": [],
            "methods_detail": [],
        }
    except Exception as parse_exc:
        return {
            "file_name": file_name,
            "file_path": rel_path,
            "package_name": None,
            "parse_status": "PARSE_ERROR",
            "parse_error": f"Unable to parse Java AST: {str(parse_exc)}",
            **line_stats,
            "class_count": 0,
            "interface_count": 0,
            "method_count": 0,
            "field_count": 0,
            "cyclomatic_complexity": 0,
            "avg_method_complexity": 0.0,
            "max_method_complexity": 0,
            "max_nesting_depth": 0,
            "import_count": 0,
            "fan_out": 0,
            "coupling_score": 0.0,
            "long_method_count": 0,
            "max_method_loc": 0,
            "max_parameters": 0,
            "maintainability_index": None,
            "halstead_volume": None,
            "code_smell_count": 0,
            "code_smells": [],
            "methods_detail": [],
        }

    # Successfully parsed AST
    package_name = tree.package.name if tree.package else "(default package)"
    import_count = len(tree.imports) if tree.imports else 0

    class_count = 0
    interface_count = 0
    field_count = 0
    declared_types = set()
    referenced_types = set()
    methods_detail = []

    long_method_threshold = thresholds.get("long_method_loc", 40)

    for _, node in tree:
        if isinstance(node, (ClassDeclaration, EnumDeclaration)):
            class_count += 1
            if node.name:
                declared_types.add(node.name)
        elif isinstance(node, InterfaceDeclaration):
            interface_count += 1
            if node.name:
                declared_types.add(node.name)
        elif isinstance(node, FieldDeclaration):
            field_count += len(node.declarators) if node.declarators else 1
        elif isinstance(node, (ReferenceType, ClassCreator)):
            t_name = node.type.name if isinstance(node, ClassCreator) and hasattr(node, "type") else getattr(node, "name", None)
            if t_name and t_name not in STANDARD_JAVA_TYPES:
                referenced_types.add(t_name)
        elif isinstance(node, (MethodDeclaration, ConstructorDeclaration)):
            start_line = node.position.line if getattr(node, "position", None) else 1
            m_loc = estimate_method_loc(source_lines, start_line)
            m_cc = compute_method_complexity(node)
            m_nesting = compute_max_nesting_depth(node, 0)
            m_params = len(node.parameters) if node.parameters else 0
            methods_detail.append(
                {
                    "name": node.name,
                    "kind": "constructor" if isinstance(node, ConstructorDeclaration) else "method",
                    "line": start_line,
                    "loc": m_loc,
                    "estimated_loc": m_loc,
                    "complexity": m_cc,
                    "cyclomatic_complexity": m_cc,
                    "parameters": m_params,
                    "max_nesting": m_nesting,
                    "max_nesting_depth": m_nesting,
                }
            )

    external_types = referenced_types - declared_types
    fan_out = len(external_types) + import_count
    # Normalized 0-100 coupling indicator where 20+ external dependencies approaches 100
    coupling_score = round(min(100.0, (fan_out / 20.0) * 100.0), 2)

    method_count = len(methods_detail)
    if method_count > 0:
        total_cc = sum(m["complexity"] for m in methods_detail)
        avg_cc = round(total_cc / method_count, 2)
        max_cc = max(m["complexity"] for m in methods_detail)
        max_nesting = max(m["max_nesting"] for m in methods_detail)
        max_m_loc = max(m["loc"] for m in methods_detail)
        max_params = max(m["parameters"] for m in methods_detail)
        long_methods = sum(1 for m in methods_detail if m["loc"] >= long_method_threshold)
    else:
        total_cc = 1 if line_stats["loc"] > 0 else 0
        avg_cc = float(total_cc)
        max_cc = total_cc
        max_nesting = 0
        max_m_loc = 0
        max_params = 0
        long_methods = 0

    halstead_vol = compute_halstead_volume(source)
    mi_score = compute_maintainability_index(
        halstead_vol, total_cc, line_stats["loc"], line_stats["comment_ratio"]
    )

    # Class-scoped observations for models trained on class-level defects.
    # A local import avoids a circular dependency with the metric helpers.
    from analyzer.class_metrics import extract_class_metrics
    classes_detail = extract_class_metrics(tree, source)

    result = {
        "classes_detail": classes_detail,
        "file_name": file_name,
        "file_path": rel_path,
        "package_name": package_name,
        "parse_status": "SUCCESS",
        "parse_error": None,
        **line_stats,
        "class_count": class_count,
        "interface_count": interface_count,
        "method_count": method_count,
        "field_count": field_count,
        "cyclomatic_complexity": total_cc,
        "avg_method_complexity": avg_cc,
        "max_method_complexity": max_cc,
        "max_nesting_depth": max_nesting,
        "import_count": import_count,
        "fan_out": fan_out,
        "coupling_score": coupling_score,
        "long_method_count": long_methods,
        "max_method_loc": max_m_loc,
        "max_parameters": max_params,
        "maintainability_index": mi_score,
        "halstead_volume": halstead_vol,
        "methods_detail": methods_detail,
    }

    smells = detect_code_smells(result, thresholds)
    result["code_smells"] = smells
    result["code_smell_count"] = len(smells)

    return result
