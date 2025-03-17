import re


def format_help_as_md(parser):
    help_text = parser.format_help()
    section = re.compile("^(.+):$")
    ret = []
    in_block = False
    for line in help_text.split("\n"):
        m = section.match(line)
        if line.startswith("usage:"):
            ret.append(line.replace("usage:", "# Usage\n```\n" + " "*6))
            in_block = True
        elif m:
            ret.append(line.replace(m.group(0), f"# {m.group(1).capitalize()}\n```"))
            in_block = True
        elif in_block and len(line) == 0:
            ret.append("```")
            in_block = False
        else:
            ret.append(line)
    return "\n".join(ret)
