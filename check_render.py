import json, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).parent

cases = [
    # 1. Five user physics/quantum examples
    (
        'CNOT gate with ketbra and mqty(...)',
        r'\[ U_{\text{CNOT}} = \ketbra{0}{0} \otimes I + \ketbra{1}{1} \otimes X = \mqty( 1 & 0 & 0 & 0 \\ 0 & 1 & 0 & 0 \\ 0 & 0 & 0 & 1 \\ 0 & 0 & 1 & 0 ) \]',
        True,
        None,
    ),
    (
        'Ising Hamiltonian + thermal state in equation env',
        r'\begin{equation} H = -J \sum_{\langle i, j \rangle} \sigma_i^z \sigma_j^z - h \sum_{i=1}^{N} \sigma_i^x, \qquad \rho_{\text{th}} = \frac{e^{-\beta H}}{\Tr\left(e^{-\beta H}\right)} = \sum_{n} \frac{e^{-\beta E_n}}{Z} \ketbra{E_n}{E_n} \end{equation}',
        True,
        None,
    ),
    (
        'Lindblad master equation with comm and acomm',
        r'$$ \frac{d\rho}{dt} = -\frac{i}{\hbar} \comm{H}{\rho} + \sum_{k} \gamma_k \left( L_k \rho L_k^\dagger - \frac{1}{2} \acomm{L_k^\dagger L_k}{\rho} \right) $$',
        True,
        None,
    ),
    (
        'Quantum teleportation in align*',
        r'\begin{align*} \ket{\Psi_0} &= \ket{\psi}_A \otimes \ket{\Phi^+}_{BC} \\ &= \left(\alpha\ket{0}_A + \beta\ket{1}_A\right) \otimes \frac{1}{\sqrt{2}}\left(\ket{00}_{BC} + \ket{11}_{BC}\right) \\ &= \frac{1}{2} \Big[ \ket{\Phi^+}_{AB} \left(\alpha\ket{0}_C + \beta\ket{1}_C\right) + \ket{\Phi^-}_{AB} \left(\alpha\ket{0}_C - \beta\ket{1}_C\right) \\ &\qquad + \ket{\Psi^+}_{AB} \left(\alpha\ket{1}_C + \beta\ket{0}_C\right) + \ket{\Psi^-}_{AB} \left(\alpha\ket{1}_C - \beta\ket{0}_C\right) \Big] \end{align*}',
        True,
        None,
    ),
    (
        'Quantum Fourier Transform',
        r'\[ U_{\text{QFT}} \ket{x} = \frac{1}{\sqrt{2^n}} \sum_{k=0}^{2^n - 1} e^{2\pi i x k / 2^n} \ket{k} = \frac{1}{2^{n/2}} \bigotimes_{j=1}^{n} \left( \ket{0} + e^{2\pi i x / 2^j} \ket{1} \right) \]',
        True,
        None,
    ),
    # 2. Bare math fragments
    (
        'Bare math: qubit + mqty',
        r'\ket{\psi} = \alpha\ket{0} + \beta\ket{1} \qquad \ket{+} \doteq \mqty( 1 \\ 0 )',
        True,
        None,
    ),
    (
        'Bare math: sum formula',
        r'\sum_{k=1}^n k = \frac{n(n+1)}{2}',
        True,
        None,
    ),
    # 3. Full physics macro coverage
    (
        'Dirac & bracket macros',
        r'\[ \bra{\phi}\ket{\psi} = \braket{\phi}{\psi} + \braket{\psi} + \braket{\phi}{A}{\psi} + \mel{n}{H}{m} + \ev{A} + \ev{H}{\psi} + \dyad{0} + \op{0}{1} \]',
        True,
        None,
    ),
    (
        'Qty, abs, norm, order, pb, eval',
        r'\[ \pb{q}{p} = \abs{x} + \norm{\vb{v}} + \order{h^2} + \qty(a+b) + \qty[c] + \qty{d} + \qty|e| + \pqty{f} + \bqty{g} + \Bqty{h} + \vqty{k} + \eval{\dv{f}{x}}_{x=0} \]',
        True,
        None,
    ),
    (
        'Matrix variants',
        r'\[ \mqty[a & b \\ c & d] + \mqty{1 & 2 \\ 3 & 4} + \mqty|1 & 0 \\ 0 & 1| + \pmqty{1 \\ 0} + \bmqty{0 \\ 1} + \vmqty{a & b \\ c & d} + \smqty(1 & 0 \\ 0 & 1) \]',
        True,
        None,
    ),
    (
        'Derivatives, vector calculus, operators',
        r'\[ \dv[2]{y}{x} + \pdv{f}{x}{y} + \fdv{S}{\phi} + \int \dd{x} + \grad\phi + \curl\va{A} + \vu{n} + \tr(M) + \rank(A) + \erf(x) + \Res_{z=0} + \diag(1,2) \qq{for} x > 0 \]',
        True,
        None,
    ),
    # 4. Tables & environments
    (
        'Tabular with booktabs',
        r'\begin{tabular}{lc} \toprule Gate & Matrix \\ \midrule $X$ & $\mqty(0 & 1 \\ 1 & 0)$ \\ \bottomrule \end{tabular}',
        True,
        None,
    ),
    (
        'Bare cases environment',
        r'f(x) = \begin{cases} x^2 & x \ge 0 \\ -x & x < 0 \end{cases}',
        True,
        None,
    ),
    (
        'Inline math delimiters',
        r'\(2x\bmod1\)',
        True,
        None,
    ),
    # 5. Prose & mixed prose + math
    (
        'Prose + inline math',
        r'The value is $x^2$ and 100% safe with a_b.',
        True,
        None,
    ),
    (
        'Pure prose with special characters',
        r'Prose: {braces}, C:\\temp, $5, 100%, a_b, #tag & more.',
        True,
        None,
    ),
    # 6. Broken LaTeX (must return ok: False with error and source)
    (
        'Undefined macro',
        r'\doesnotexist',
        False,
        r'\doesnotexist',
    ),
    (
        'Unclosed dollar math',
        r'$\frac{1}{',
        False,
        None,
    ),
    (
        'Unclosed inline math in prose',
        r'The broken formula is $\frac{1}{',
        False,
        None,
    ),
    (
        'Unclosed \\( delimiter',
        r'\(x',
        False,
        None,
    ),
    # 7. Security rejection probes & empty input
    (
        'Empty input',
        '',
        False,
        None,
    ),
    (
        'Security: \\input',
        r'\input{/etc/passwd}',
        False,
        None,
    ),
    (
        'Security: ^^ control-character escape',
        r'$\^^69nput{/etc/passwd}$',
        False,
        None,
    ),
    (
        'Security: \\pdfmdfivesum',
        r'$\pdfmdfivesum file {/etc/passwd}$',
        False,
        None,
    ),
    (
        'Security: \\@@input',
        r'$\@@input /etc/passwd$',
        False,
        None,
    ),
]

for label, source, expected, expected_error_substr in cases:
    with tempfile.TemporaryDirectory() as d:
        Path(d, 'input.txt').write_text(source)
        p = subprocess.run([sys.executable, str(root / 'render.py'), d], capture_output=True, text=True, timeout=25)
        assert p.stdout.strip(), f'Empty stdout for {label}: stderr={p.stderr}'
        result = json.loads(p.stdout)
        assert result['ok'] == expected, (label, source, result, p.stderr)
        if expected:
            assert result['width'] > 0 and result['height'] > 0, (label, result)
            assert (Path(d) / 'image.png').is_file(), (label, 'missing image.png')
            print(f'PASS [{result["width"]}x{result["height"]}]: {label}')
        else:
            assert result.get('error'), (label, result)
            assert result.get('source') == source.strip(), (label, result)
            if expected_error_substr:
                assert expected_error_substr in result['error'], (label, result)
            print(f'PASS rejected ({result["error"]}): {label}')

print(f'\nALL {len(cases)} TESTS PASSED!')
