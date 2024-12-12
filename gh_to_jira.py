import re
import sys
from html.parser import HTMLParser


class GhToJira(HTMLParser):
    def __init__(self):
        super().__init__()
        self.a_ref_url = None
        self.a_ref_text = ""
        self.ul = False
        self.ul_text = ""
        self.ol = False
        self.ol_text = ""
        self.text = ""
        self.line = ""
        self.pre = False
        self.blockquote = False
        self.code = False
        self.code_text = ""

    def print_or_store(self, text, last_line=False):
        """print the text or store in buffer if we have an active a-tag"""
        if self.code:
            self.code_text += text
            return

        if self.a_ref_url:
            self.a_ref_text += text
            return

        if self.ol:
            self.ol_text += text
            return

        if self.ul:
            self.ul_text += text
            return

        self.line += text

        if not text.endswith('\n'):
            return

        # <hr/> is "---" in github but "----" in jira
        if self.line.strip() == "---":
            self.line = self.line.strip() + "-\n"

        if self.blockquote and len(self.line.strip()):
            # special case for headings and list:
            prefix = ""
            m = re.match(r'(h[1-9]\.|\*|#) ', self.line)
            if m:
                prefix = self.line[:m.end()]
                self.line = self.line[m.end():]

            self.text += f"{prefix}??{self.line.rstrip()}??"
            if not last_line:
                self.text += "\n"
        else:
            if last_line:
                self.line = self.line.rstrip()
            self.text += self.line
        self.line = ""

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            if attrs[0][0] != 'href':
                print("Warning: Tag 'a' is not a 'href' tag", file=sys.stderr)
                return
            self.a_ref_url = attrs[0][1]
        elif re.match(r'h[1-9]', tag):
            self.print_or_store(f"{tag}. ")
        elif tag == 'blockquote':
            self.blockquote = True
        elif tag == 'ul':
            self.ul = True
        elif tag == 'ol':
            self.ol = True
        elif tag == 'li':
            # usually just a newline between <ul> and <li> - we'll ignore that
            if self.ul:
                self.ul_text = self.ul_text.strip()
            if self.ol:
                self.ol_text = self.ol_text.strip()
        elif tag == 'em':
            self.print_or_store("_")
        elif tag == 'code':
            self.code = True
        elif tag == 'pre':
            self.pre = True
        elif tag == 'hr':
            self.print_or_store("----\n")

    def handle_endtag(self, tag):
        if tag == 'a':
            url = self.a_ref_url
            text = self.a_ref_text

            # reset first, so `print_or_store()` works
            self.a_ref_url = None
            self.a_ref_text = ""

            if text:
                self.print_or_store(f"[{text}|{url}]")
            else:
                self.print_or_store(f"[{url}]")
        elif tag == 'blockquote':
            self.blockquote = False
        elif tag == 'ol':
            self.ol = False
        elif tag == 'ul':
            self.ul = False
        elif tag == 'li':
            if self.ul:
                # reset shortly, so `print_or_store()` works
                self.ul = False
                self.print_or_store(f"* {self.ul_text}\n")
                self.ul_text = ""
                self.ul = True
            elif self.ol:
                # reset shortly, so `print_or_store()` works
                self.ol = False
                self.print_or_store(f"* {self.ol_text}")
                self.ol_text = ""
                self.ol = True
        elif tag == 'em':
            self.print_or_store("_")
        elif tag == 'code':
            self.code = False
            if '\n' in self.code_text.strip():
                self.print_or_store("\n{code}\n" + self.code_text + "\n{code\n")
            else:
                self.print_or_store("{{" + self.code_text + "}}")
            self.code_text = ""
        elif tag == 'p':
            self.print_or_store("\n")
        elif tag == 'pre':
            self.pre = False

    def handle_data(self, data):
        self.print_or_store(data)

    def unknown_decl(self, data):
        self.print_or_store(data)

    def __str__(self):
        # finish the last line
        self.print_or_store("\n", last_line=True)
        return self.text
