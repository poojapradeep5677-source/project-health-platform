"""Extract class-scoped Java metrics for the Ant 1.7 research classifier.

The legacy analyzer produces FILE-level metrics. The training rows are classes,
so passing entire-file LOC/complexity into that model is a unit-of-analysis
mismatch. This module extracts one observation for each named class or enum.

Method-based WMC here is an approximation to the original Jureczko WMC, and
LOC counting may differ across tools. It does not solve cross-project shift.
"""
from bisect import bisect_right
from javalang.tokenizer import tokenize
from javalang.tree import (
    ClassDeclaration, EnumDeclaration, MethodDeclaration, ConstructorDeclaration
)
from analyzer.java_analyzer import count_lines_and_comments, compute_method_complexity


def extract_class_metrics(ast, source: str) -> list[dict]:
    """Return separate, named class metrics; never silently substitute file totals."""
    tokens = list(tokenize(source))
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def absolute_pos(token):
        pos = token.position
        if not pos or pos.line < 1 or pos.line > len(lines):
            return None
        return offsets[pos.line - 1] + pos.column - 1

    token_offsets = [absolute_pos(t) for t in tokens]
    observations = []

    for path, node in ast:
        if not isinstance(node, (ClassDeclaration, EnumDeclaration)):
            continue
        if not node.position:
            continue

        start = offsets[node.position.line - 1] + node.position.column - 1
        # Java tokenization excludes braces in comments and string literals.
        opening = next(
            (i for i, (t, pos) in enumerate(zip(tokens, token_offsets))
             if pos is not None and pos >= start and t.value == "{"),
            None,
        )
        if opening is None:
            continue
        depth = 0
        closing = None
        for i in range(opening, len(tokens)):
            if tokens[i].value == "{":
                depth += 1
            elif tokens[i].value == "}":
                depth -= 1
                if depth == 0:
                    closing = i
                    break
        if closing is None or token_offsets[closing] is None:
            continue

        end = token_offsets[closing] + 1
        class_source = source[start:end]
        class_loc = count_lines_and_comments(class_source)["loc"]

        # Only direct members belong to this class. Nested class methods should
        # be counted for their own observation, not added to the outer WMC.
        body = getattr(node, "body", []) or []
        if not isinstance(body, list):  # EnumBody stores declarations separately
            body = getattr(body, "declarations", []) or []
        direct_methods = [
            member for member in body
            if isinstance(member, (MethodDeclaration, ConstructorDeclaration))
        ]
        wmc = sum(compute_method_complexity(method) for method in direct_methods)
        parent_names = [
            p.name for p in path
            if isinstance(p, (ClassDeclaration, EnumDeclaration)) and getattr(p, "name", None)
        ]
        qualified_name = ".".join([*parent_names, node.name])
        observations.append({
            "class_name": qualified_name,
            "kind": "enum" if isinstance(node, EnumDeclaration) else "class",
            "start_line": node.position.line,
            "end_line": tokens[closing].position.line,
            "loc": int(class_loc),
            # ML model feature name expected by existing predictor.
            "cyclomatic_complexity": int(wmc),
            "wmc": int(wmc),
            "method_count": len(direct_methods),
            "parse_status": "SUCCESS",
        })
    return observations
