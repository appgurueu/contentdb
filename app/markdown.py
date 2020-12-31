import bleach
from markdown import Markdown
from flask import Markup

# Whitelist source: MIT
#
# https://github.com/Wenzil/mdx_bleach/blob/master/mdx_bleach/whitelist.py

"""
Default whitelist of allowed HTML tags. Any other HTML tags will be escaped or
stripped from the text. This applies to the html output that Markdown produces.
"""
ALLOWED_TAGS = [
	'ul',
	'ol',
	'li',
	'p',
	'pre',
	'code',
	'blockquote',
	'h1',
	'h2',
	'h3',
	'h4',
	'h5',
	'h6',
	'hr',
	'br',
	'strong',
	'em',
	'a',
	'img'
]

"""
Default whitelist of attributes. It allows the href and title attributes for <a>
tags and the src, title and alt attributes for <img> tags. Any other attribute
will be stripped from its tag.
"""
ALLOWED_ATTRIBUTES = {
	'a': ['href', 'title'],
	'img': ['src', 'title', 'alt']
}

"""
If you allow tags that have attributes containing a URI value
(like the href attribute of an anchor tag,) you may want to adapt
the accepted protocols. The default list only allows http, https and mailto.
"""
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


md = Markdown(extensions=["fenced_code"], output_format="html5")

def render_markdown(source):
	return bleach.clean(md.convert(source),
			tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
			styles=[], protocols=ALLOWED_PROTOCOLS)

def init_app(app):
	@app.template_filter()
	def markdown(source):
		return Markup(render_markdown(source))
