import json, os, re, resource, signal, subprocess, sys
from pathlib import Path

child = None
def cancel(*_):
    if child is not None and child.poll() is None:
        os.killpg(child.pid, signal.SIGKILL)
    raise SystemExit(130)
signal.signal(signal.SIGTERM, cancel)

# The app bundles Pillow here so the worker can keep user site packages disabled.
sys.path.insert(0, str(Path(__file__).resolve().parent/'python'))
from PIL import Image, ImageFilter

PREAMBLE = r"""\documentclass[12pt]{article}
\usepackage[margin=0.5in]{geometry}
\usepackage{amsmath,amssymb,mathtools,bm,array,booktabs}
\providecommand{\mathscr}[1]{\mathcal{#1}}
\pagestyle{empty}
\makeatletter
% Dirac notation
\NewDocumentCommand{\ket}{s m}{\IfBooleanTF{#1}{\lvert #2 \rangle}{\left\lvert #2 \right\rangle}}
\NewDocumentCommand{\bra}{s m}{\IfBooleanTF{#1}{\langle #2 \rvert}{\left\langle #2 \right\rvert}}
\NewDocumentCommand{\braket}{s m}{%
  \@ifnextchar\bgroup{\mathpeek@braket@two{#1}{#2}}{%
    \IfBooleanTF{#1}{\langle #2 \vert #2 \rangle}{\left\langle #2 \middle\vert #2 \right\rangle}%
  }%
}
\NewDocumentCommand{\mathpeek@braket@two}{m m m}{%
  \@ifnextchar\bgroup{\mathpeek@braket@three{#1}{#2}{#3}}{%
    \IfBooleanTF{#1}{\langle #2 \vert #3 \rangle}{\left\langle #2 \middle\vert #3 \right\rangle}%
  }%
}
\NewDocumentCommand{\mathpeek@braket@three}{m m m m}{%
  \IfBooleanTF{#1}{\langle #2 \vert #3 \vert #4 \rangle}{\left\langle #2 \middle\vert #3 \middle\vert #4 \right\rangle}%
}
\NewDocumentCommand{\ketbra}{s m}{%
  \@ifnextchar\bgroup{\mathpeek@ketbra@two{#1}{#2}}{%
    \IfBooleanTF{#1}{\lvert #2 \rangle\langle #2 \rvert}{\left\lvert #2 \right\rangle\!\left\langle #2 \right\rvert}%
  }%
}
\NewDocumentCommand{\mathpeek@ketbra@two}{m m m}{%
  \IfBooleanTF{#1}{\lvert #2 \rangle\langle #3 \rvert}{\left\lvert #2 \right\rangle\!\left\langle #3 \right\rvert}%
}
\NewDocumentCommand{\dyad}{}{\ketbra}
\NewDocumentCommand{\op}{}{\ketbra}
\NewDocumentCommand{\ev}{s m}{%
  \@ifnextchar\bgroup{\mathpeek@ev@two{#1}{#2}}{%
    \IfBooleanTF{#1}{\langle #2 \rangle}{\left\langle #2 \right\rangle}%
  }%
}
\NewDocumentCommand{\mathpeek@ev@two}{m m m}{%
  \IfBooleanTF{#1}{\langle #3 \rvert #2 \lvert #3 \rangle}{\left\langle #3 \middle\vert #2 \middle\vert #3 \right\rangle}%
}
\NewDocumentCommand{\mel}{s m m m}{%
  \IfBooleanTF{#1}{\langle #2 \rvert #3 \lvert #4 \rangle}{\left\langle #2 \middle\vert #3 \middle\vert #4 \right\rangle}%
}
% Commutators & brackets
\NewDocumentCommand{\comm}{s m m}{\IfBooleanTF{#1}{[#2, #3]}{\left[#2, #3\right]}}
\NewDocumentCommand{\acomm}{s m m}{\IfBooleanTF{#1}{\{#2, #3\}}{\left\{#2, #3\right\}}}
\NewDocumentCommand{\pb}{s m m}{\IfBooleanTF{#1}{\{#2, #3\}}{\left\{#2, #3\right\}}}
\NewDocumentCommand{\abs}{s m}{\IfBooleanTF{#1}{\lvert #2 \rvert}{\left\lvert #2 \right\rvert}}
\NewDocumentCommand{\norm}{s m}{\IfBooleanTF{#1}{\lVert #2 \rVert}{\left\lVert #2 \right\rVert}}
\NewDocumentCommand{\order}{s m}{\mathcal{O}\IfBooleanTF{#1}{(#2)}{\left(#2\right)}}
\NewDocumentCommand{\pqty}{s m}{\IfBooleanTF{#1}{(#2)}{\left(#2\right)}}
\NewDocumentCommand{\bqty}{s m}{\IfBooleanTF{#1}{[#2]}{\left[#2\right]}}
\NewDocumentCommand{\Bqty}{s m}{\IfBooleanTF{#1}{\{#2\}}{\left\{#2\right\}}}
\NewDocumentCommand{\vqty}{s m}{\IfBooleanTF{#1}{\lvert #2 \rvert}{\left\lvert #2 \right\rvert}}
\NewDocumentCommand{\mathpeek@vqty}{r||}{\left\lvert #1 \right\rvert}
\NewDocumentCommand{\mathpeek@vqty@star}{r||}{\lvert #1 \rvert}
\NewDocumentCommand{\mathpeek@qty@brace}{m m}{\IfBooleanTF{#1}{\{#2\}}{\left\{#2\right\}}}
\NewDocumentCommand{\qty}{s d() d[]}{%
  \IfValueTF{#2}{\IfBooleanTF{#1}{(#2)}{\left(#2\right)}}{%
    \IfValueTF{#3}{\IfBooleanTF{#1}{[#3]}{\left[#3\right]}}{%
      \@ifnextchar\bgroup{\mathpeek@qty@brace{#1}}{%
        \IfBooleanTF{#1}{\mathpeek@vqty@star}{\mathpeek@vqty}%
      }%
    }%
  }%
}
\NewDocumentCommand{\eval}{s m}{\IfBooleanTF{#1}{#2\rvert}{\left. #2 \right\rvert}}
% Matrices
\NewDocumentCommand{\pmqty}{m}{\begin{pmatrix}#1\end{pmatrix}}
\NewDocumentCommand{\bmqty}{m}{\begin{bmatrix}#1\end{bmatrix}}
\NewDocumentCommand{\Bmqty}{m}{\begin{Bmatrix}#1\end{Bmatrix}}
\NewDocumentCommand{\vmqty}{m}{\begin{vmatrix}#1\end{vmatrix}}
\NewDocumentCommand{\mathpeek@vmqty}{r||}{\begin{vmatrix}#1\end{vmatrix}}
\NewDocumentCommand{\mathpeek@mqty@brace}{m}{\begin{matrix}#1\end{matrix}}
\NewDocumentCommand{\mqty}{d() d[]}{%
  \IfValueTF{#1}{\begin{pmatrix}#1\end{pmatrix}}{%
    \IfValueTF{#2}{\begin{bmatrix}#2\end{bmatrix}}{%
      \@ifnextchar\bgroup{\mathpeek@mqty@brace}{\mathpeek@vmqty}%
    }%
  }%
}
\NewDocumentCommand{\mathpeek@svmqty}{r||}{\left\lvert\begin{smallmatrix}#1\end{smallmatrix}\right\rvert}
\NewDocumentCommand{\mathpeek@smqty@brace}{m}{\begin{smallmatrix}#1\end{smallmatrix}}
\NewDocumentCommand{\smqty}{d() d[]}{%
  \IfValueTF{#1}{\left(\begin{smallmatrix}#1\end{smallmatrix}\right)}{%
    \IfValueTF{#2}{\left[\begin{smallmatrix}#2\end{smallmatrix}\right]}{%
      \@ifnextchar\bgroup{\mathpeek@smqty@brace}{\mathpeek@svmqty}%
    }%
  }%
}
% Derivatives & vector calculus
\NewDocumentCommand{\dd}{o}{\mathop{}\!\mathrm{d}\IfValueT{#1}{^{#1}}}
\NewDocumentCommand{\dv}{s o m}{%
  \@ifnextchar\bgroup{\mathpeek@dv@two{#2}{#3}}{%
    \frac{\mathrm{d}\IfValueT{#2}{^{#2}}}{\mathrm{d}#3\IfValueT{#2}{^{#2}}}%
  }%
}
\NewDocumentCommand{\mathpeek@dv@two}{m m m}{%
  \frac{\mathrm{d}\IfValueT{#1}{^{#1}} #2}{\mathrm{d}#3\IfValueT{#1}{^{#1}}}%
}
\NewDocumentCommand{\pdv}{s o m}{%
  \@ifnextchar\bgroup{\mathpeek@pdv@two{#2}{#3}}{%
    \frac{\partial\IfValueT{#2}{^{#2}}}{\partial #3\IfValueT{#2}{^{#2}}}%
  }%
}
\NewDocumentCommand{\mathpeek@pdv@two}{m m m}{%
  \@ifnextchar\bgroup{\mathpeek@pdv@three{#2}{#3}}{%
    \frac{\partial\IfValueT{#1}{^{#1}} #2}{\partial #3\IfValueT{#1}{^{#1}}}%
  }%
}
\NewDocumentCommand{\mathpeek@pdv@three}{m m m}{%
  \frac{\partial^2 #1}{\partial #2 \partial #3}%
}
\NewDocumentCommand{\fdv}{s o m}{%
  \@ifnextchar\bgroup{\mathpeek@fdv@two{#2}{#3}}{%
    \frac{\delta\IfValueT{#2}{^{#2}}}{\delta #3\IfValueT{#2}{^{#2}}}%
  }%
}
\NewDocumentCommand{\mathpeek@fdv@two}{m m m}{%
  \frac{\delta\IfValueT{#1}{^{#1}} #2}{\delta #3\IfValueT{#1}{^{#1}}}%
}
\NewDocumentCommand{\grad}{}{\boldsymbol{\nabla}}
\NewDocumentCommand{\curl}{}{\boldsymbol{\nabla}\times}
\NewDocumentCommand{\vb}{s m}{\IfBooleanTF{#1}{\bm{#2}}{\mathbf{#2}}}
\NewDocumentCommand{\va}{s m}{\vec{\IfBooleanTF{#1}{\bm{#2}}{\mathbf{#2}}}}
\NewDocumentCommand{\vu}{s m}{\hat{\IfBooleanTF{#1}{\bm{#2}}{\mathbf{#2}}}}
% Operators
\DeclareMathOperator{\Tr}{Tr}
\DeclareMathOperator{\tr}{tr}
\DeclareMathOperator{\rank}{rank}
\DeclareMathOperator{\erf}{erf}
\DeclareMathOperator{\Res}{Res}
\DeclareMathOperator{\diag}{diag}
\NewDocumentCommand{\qq}{s m}{\IfBooleanTF{#1}{\text{#2}\quad}{\quad\text{#2}\quad}}
\makeatother
"""

def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32*1024*1024, 32*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

def sandbox_profile(folder, allowed_executables):
    # The TeX input is user-controlled. Keep its process tree away from user
    # files and the network; its only writable location is this private job dir.
    q = lambda value: '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'
    resolved_folder = q(Path(folder).resolve())
    rules = ['(version 1)', '(deny default)', '(deny network*)', '(allow process-fork)', '(allow file-read*)',
             '(deny file-read* (subpath ' + q(Path.home()) + '))',
             '(deny file-read* (subpath "/Users"))',
             '(deny file-read* (subpath "/Volumes"))',
             '(deny file-read* (subpath "/tmp"))',
             '(deny file-read* (subpath "/private/tmp"))',
             '(allow file-read* (subpath ' + resolved_folder + '))',
             '(allow file-write* (subpath ' + resolved_folder + '))']
    # Keep the supplied path as well as its canonical path: TeX and Homebrew
    # tools are often symlinks, and seatbelt checks the path used for exec.
    for path in allowed_executables:
        for executable in dict.fromkeys((str(path), str(Path(path).resolve()))):
            rules.append('(allow process-exec (literal ' + q(executable) + '))')
    return '\n'.join(rules)

def extract_tex_error(lines):
    for idx, line in enumerate(lines):
        if not line.startswith('! '):
            continue
        msg = line[2:].strip()
        if 'Undefined control sequence' in msg:
            for follow in lines[idx + 1:idx + 6]:
                macros = re.findall(r'\\[a-zA-Z@]+', follow)
                if macros:
                    return f'Undefined control sequence: {macros[-1]}'
        return msg[:300]
    for line in lines:
        if line.startswith('!'):
            return line[1:].strip()[:300]
    return 'The renderer could not process this expression.'

def run(args, folder, *, sandbox=False):
    global child
    (folder/'texmf-var').mkdir(mode=0o700, exist_ok=True)
    (folder/'texmf-config').mkdir(mode=0o700, exist_ok=True)
    env = {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin', 'HOME':str(folder), 'TMPDIR':str(folder),
           'openin_any':'p', 'openout_any':'p', 'shell_escape':'f', 'TEXMFOUTPUT':str(folder),
           'TEXMFVAR':str(folder/'texmf-var'), 'TEXMFCONFIG':str(folder/'texmf-config'), 'TEXMFHOME':str(folder)}
    command = args
    if sandbox:
        sandbox_exec = '/usr/bin/sandbox-exec'
        if not os.path.isfile(sandbox_exec):
            raise ValueError('The macOS renderer sandbox is unavailable; rendering was stopped for safety.')
        command = [sandbox_exec, '-p', sandbox_profile(folder, args[:1]), '--', *args]
    with open(folder/'process.log', 'wb') as log:
        child = subprocess.Popen(command, cwd=folder, env=env, stdout=log, stderr=log,
                                 start_new_session=True, preexec_fn=limits)
        try:
            code = child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise ValueError('This expression took too long to render. Try a smaller selection.')
    if code:
        lines = (folder/'process.log').read_text(errors='replace').splitlines()
        sandbox_error = next((line for line in lines if 'sandbox' in line.lower()), None)
        if sandbox_error:
            raise RuntimeError('The renderer sandbox blocked this process: ' + sandbox_error[:250])
        raise ValueError(extract_tex_error(lines)[:300])

def latex_escape(text):
    table = {'\\': '/', '{': r'\{', '}': r'\}',
             '%': r'\%', '#': r'\#', '&': r'\&', '_': r'\_',
             '$': r'{\symbol{36}}', '^': r'\textasciicircum{}', '~': r'\textasciitilde{}'}
    return ''.join(table.get(c, c) for c in text)

DISPLAY_ENVS = r'align\*?|equation\*?|gather\*?|multline\*?|flalign\*?|displaymath'
INNER_MATH_ENVS = r'cases|pmatrix|bmatrix|vmatrix|Bmatrix|Vmatrix|matrix|split'
RAW_TEXT_ENVS = r'tabular'

INLINE_RE = re.compile(r'\$(?!\s)(.+?)(?<!\\)\$|\\\((.+?)\\\)', re.S)
TOP_BLOCK_RE = re.compile(
    rf'\\begin\{{(?P<disp>{DISPLAY_ENVS})\}}.*?\\end\{{(?P=disp)\}}'
    rf'|\\begin\{{(?P<raw>{RAW_TEXT_ENVS})\}}.*?\\end\{{(?P=raw)\}}'
    rf'|\$\$.+?\$\$|\\\[.+?\\\]',
    re.S,
)
INNER_ENV_RE = re.compile(
    rf'\\begin\{{(?P<inner>{INNER_MATH_ENVS})\}}.*?\\end\{{(?P=inner)\}}',
    re.S,
)

def is_bare_math(text):
    """Detect bare LaTeX math fragments without explicit $...$ or \\[...\\] delimiters."""
    s = text.strip()
    if not s:
        return False
    # Explicit inline delimiters mean this chunk is prose + inline math (or unclosed).
    if INLINE_RE.search(s):
        return False
    # Strong prose markers (Windows paths, currency, unescaped %, hashtags).
    if re.search(r'[A-Za-z]:\\|\$\d|\d(?<!\\)%|#\w', s):
        return False
    # Remove text-mode macro arguments and LaTeX command names before counting prose words.
    stripped = re.sub(r'\\(?:text|mathrm|mathbf|mathit|mathsf|mathtt|operatorname|mbox|qq|textbf|textit|label)\*?\{[^{}]*\}', ' ', s)
    stripped = re.sub(r'\\begin\{[^}]*\}|\\end\{[^}]*\}', ' ', stripped)
    stripped = re.sub(r'\\[a-zA-Z]+', ' ', stripped)
    prose_words = re.findall(r'\b[A-Za-z]{2,}\b', stripped)
    if len(prose_words) >= 4:
        return False
    # Bare LaTeX command (e.g. \ket{\psi}, \sum_{k=1}^n, \doesnotexist)
    if re.search(r'\\[a-zA-Z]+', s):
        return True
    # Pure equation without backslash commands (e.g. E = mc^2, x^2 + y^2 = r^2)
    if '=' in s and re.search(r'[\^_+\-*/()]', s) and len(prose_words) <= 1:
        return True
    return False

def check_unclosed_math(text):
    """Reject clearly unclosed math delimiters so broken formulas report an error."""
    if re.search(r'(?<!\\)\\\[', text) or '$$' in text:
        raise ValueError('Unclosed display math delimiter.')
    if re.search(r'(?<!\\)\\\(', text):
        raise ValueError('Unclosed inline math delimiter \\(.')
    if re.search(r'(?<!\\)\$(?!\d)[^\n$]*\\[a-zA-Z]+', text):
        raise ValueError('Unclosed inline math delimiter $.')

def render_prose_with_inline(value):
    chunks, cursor = [], 0
    for m in INLINE_RE.finditer(value):
        before = value[cursor:m.start()]
        check_unclosed_math(before)
        chunks.append(latex_escape(before))
        expr = m.group(1) if m.group(1) is not None else m.group(2)
        chunks.append('$' + expr.strip() + '$')
        cursor = m.end()
    tail = value[cursor:]
    check_unclosed_math(tail)
    chunks.append(latex_escape(tail))
    prose = ''.join(chunks).replace('\r\n', '\n').replace('\r', '\n')
    return [p.strip() for p in re.split(r'\n\s*\n', prose) if p.strip()]

def mixed_body(text):
    """Convert ordinary clipboard prose, bare math, and explicit LaTeX environments to safe TeX."""
    if '\\documentclass' in text:
        raise ValueError('Select a passage or formula, not a complete TeX document.')
    tokens, pos = [], 0
    for match in TOP_BLOCK_RE.finditer(text):
        if match.start() > pos:
            tokens.append(('text', text[pos:match.start()]))
        raw = match.group()
        if match.group('disp') is not None or match.group('raw') is not None:
            tokens.append(('raw', raw))
        else:
            tokens.append(('display', raw[2:-2].strip()))
        pos = match.end()
    if pos < len(text):
        tokens.append(('text', text[pos:]))
    if not tokens:
        tokens = [('text', text)]

    out = []
    for kind, value in tokens:
        if kind == 'raw':
            out.append(value)
            continue
        if kind == 'display':
            out.append(r'\[' + value + r'\]')
            continue
        if is_bare_math(value):
            # Still reject unclosed explicit math delimiters inside bare fragments.
            if re.search(r'(?<!\\)\\\[|\$\$|(?<!\\)\\\(|(?<!\\)\$(?!\d)', value):
                check_unclosed_math(value)
            out.append(r'\[' + value.strip() + r'\]')
            continue
        # Handle inner math environments embedded inside prose.
        sub_pos = 0
        for inner in INNER_ENV_RE.finditer(value):
            if inner.start() > sub_pos:
                out.extend(render_prose_with_inline(value[sub_pos:inner.start()]))
            out.append(r'\[' + inner.group() + r'\]')
            sub_pos = inner.end()
        if sub_pos < len(value):
            out.extend(render_prose_with_inline(value[sub_pos:]))
    return '\n\\par\n'.join(out) or r'\textit{No text selected.}'

def render(folder):
    s = (folder/'input.txt').read_text().strip()
    if not s: raise ValueError('Select a LaTeX expression first.')
    if len(s.encode()) > 32768: raise ValueError('Select a smaller expression (up to 32 KB).')
    if s.startswith('```'):
        match = re.fullmatch(r'```(?:latex|tex|math)?\s*\n(.*?)\n```', s, re.S)
        if not match: raise ValueError('Copy the complete LaTeX code block, including its closing fence.')
        s = match[1].strip()
    if '^^' in s:
        raise ValueError('This preview supports math fragments, not TeX control-character escapes.')
    if re.search(r'\\(?:@*input|include|openin|openout|read|write|newread|newwrite|immediate|closein|closeout|catcode|csname|def|edef|gdef|xdef|let|futurelet|chardef|mathchardef|toks|loop|repeat|usepackage|RequirePackage|LoadClass|ProvidesPackage|verbatiminput|lstinputlisting|special|directlua|pdfobj|pdffiledump|pdfmdfivesum|pdffilesize|pdfcreationdate|pdftexbanner|pdftexversion|pdfximage|pdfrefximage|pdfincludechars|pdfmapfile|pdfmapline|pdfpageattr|pdfcatalog|pdfinfo|pdfnames|pdfoutline|pdfannot|scantokens|everypar|everymath|everydisplay|output|aftergroup|afterassignment|expandafter|noexpand|meaning|string|show|showthe|font|ifeof|ifx|ifdefined|ifcsname)\b', s):
        raise ValueError('This preview supports math fragments, not file access or TeX programming commands.')
    body = mixed_body(s)
    tex = '/Library/TeX/texbin/pdflatex'
    cairo = '/opt/homebrew/bin/pdftocairo'
    info = '/opt/homebrew/bin/pdfinfo'
    for executable in (tex, cairo, info):
        if not os.path.isfile(executable): raise ValueError('Missing renderer: '+executable)
    (folder/'render.tex').write_text(PREAMBLE + '\\begin{document}\n' + body + '\n\\end{document}\n')
    run([tex, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', 'render.tex'], folder, sandbox=True)
    run([info, 'render.pdf'], folder, sandbox=True)
    pages = re.search(r'^Pages:\s+(\d+)', (folder/'process.log').read_text(), re.M)
    if not pages or int(pages[1]) != 1: raise ValueError('This selection spans multiple pages. Select one expression at a time.')
    run([cairo,'-singlefile','-png','-transp','-r','300','render.pdf','image'], folder, sandbox=True)
    with Image.open(folder/'image.png') as original:
        if original.width * original.height > 20_000_000: raise ValueError('The rendered expression is too large.')
        im = original.convert('RGBA')
    box = im.getchannel('A').getbbox()
    if not box: raise ValueError('The selection did not produce a visible formula.')
    im = im.crop(box)
    # Slightly strengthen fine strokes at source resolution (0.32 screen points/pixel).
    alpha = im.getchannel('A')
    alpha = Image.blend(alpha, alpha.filter(ImageFilter.MaxFilter(3)), 0.25)
    im.putalpha(alpha)
    im.save(folder/'image.png')
    return {'ok':True, 'width':im.width, 'height':im.height}

if __name__ == '__main__':
    folder = Path(sys.argv[1])
    try:
        result = render(folder)
    except Exception as e:
        source = ''
        try:
            source = (folder/'input.txt').read_text(errors='replace').strip()
        except Exception:
            pass
        result = {'ok': False, 'error': str(e)[:400], 'source': source}
    print(json.dumps(result))
