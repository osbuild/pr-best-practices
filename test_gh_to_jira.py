import unittest

from gh_to_jira import GhToJira


class TestPRChecks(unittest.TestCase):

    def test_plain_text(self):
        p = GhToJira()
        p.feed("hello")
        self.assertEqual("hello", str(p))

    def test_plain_text_newline(self):
        p = GhToJira()
        p.feed("hello\n")
        self.assertEqual("hello\n", str(p))

    def test_plain_text_with_html(self):
        p = GhToJira()
        p.feed("""hello
<H1>Title</H1>
finally
""")
        self.assertEqual("""hello
h1. Title
finally
""", str(p))

    def test_ul(self):
        p = GhToJira()
        p.feed("""<ul>
<li>1</li>
<li>2</li>
</ul>""")
        self.assertEqual("""* 1
* 2
""", str(p))

    def test_ul_oneline(self):
        p = GhToJira()
        p.feed("""<ul><li>1</li><li>2</li></ul>""")
        self.assertEqual("""* 1
* 2
""", str(p))

    def test_complex_example1(self):
        p = GhToJira()
        p.feed("""<details>
<summary>Release notes</summary>
<p><em>Sourced from <a href="https://github.com/eslint/eslint/releases">eslint's releases</a>.</em></p>
<blockquote>
<h2>v9.16.0</h2>
<h2>Features</h2>
""")
        self.assertEqual("""
Release notes
_Sourced from [eslint's releases|https://github.com/eslint/eslint/releases]._


h2. ??v9.16.0??
h2. ??Features??
""", str(p))

    def test_complex_example2(self):
        p = GhToJira()
        p.feed("""
<ul>
<li><a href="https://github.com/URL1"><code>cbf7db0</code></a> 9.16.0</li>
<li><a href="https://github.com/URL2"><code>715ba8b</code></a> Build: changelog update for 9.16.0</li>
</ul>""")
        self.assertEqual("""
* [{{cbf7db0}}|https://github.com/URL1] 9.16.0
* [{{715ba8b}}|https://github.com/URL2] Build: changelog update for 9.16.0
""", str(p))
