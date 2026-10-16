"""tailwind.py — utility-class declarations for the static cascade.

impeccable's static engine never turns Tailwind utility classes into computed styles: classes only feed the rules'
own regex heuristics over the class corpus (side-tab `border-l-4`, gradient-text `bg-clip-text`, ai-color-palette
`from-violet-*`, cream-palette's 8-entry hex table). We match that, so class_decls returns nothing and each rule that
reads classes does so itself (rules_*.py). Kept as the one place to add a mapping if parity is ever traded for reach.
"""


def class_decls(node):
    return []
