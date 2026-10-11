# How Seam works

The derivations behind the [README](../README.md): why one Bell pair is enough for a gate between two traps, when one pair can serve many gates, what the noisy link does to the pair, what distillation does to this particular noise, and why choosing the bursts is a vertex cover. Every number is reproduced by a command here or in [CLAIMS.md](../CLAIMS.md).

Notation. Trap A holds the control qubit $c$ and a link ion $a$. Trap B holds a link ion $b$ and the target $t$. The link has prepared $a$ and $b$ in the Bell state $|\Phi^+\rangle = (|00\rangle + |11\rangle)/\sqrt{2}$. The data qubits are in an arbitrary state, which we split along the control:

$$|\psi\rangle = \alpha\,|0\rangle_c|\phi_0\rangle + \beta\,|1\rangle_c|\phi_1\rangle .$$

Here $|\phi_0\rangle$ and $|\phi_1\rangle$ are normalized states of all the other data qubits, in both traps.

## 1. The cat-entangler

Apply `cx(c, a)`, a gate local to Trap A:

$$\frac{1}{\sqrt{2}}\Big[\alpha\,|0\rangle_c\big(|00\rangle + |11\rangle\big)_{ab}|\phi_0\rangle + \beta\,|1\rangle_c\big(|10\rangle + |01\rangle\big)_{ab}|\phi_1\rangle\Big].$$

Measure $a$ and send the outcome $m$ to Trap B, which applies $X^m$ to $b$. If $m = 0$ the remaining qubits are in

$$|\mathrm{cat}\rangle = \alpha\,|0\rangle_c|0\rangle_b|\phi_0\rangle + \beta\,|1\rangle_c|1\rangle_b|\phi_1\rangle . \tag{1}$$

If $m = 1$ they are in the same state with $b$ inverted, and the $X$ on $b$ restores (1). Both outcomes have probability 1/2 and say nothing about $\alpha$ or $\beta$. The link ion $b$ is now a copy of the control in the Z basis. It is not a clone: the amplitudes are shared between $c$ and $b$, as in a cat state.

## 2. The gate, and the cat-disentangler

Let $G$ be any gate that is diagonal in Z on the control, $G = |0\rangle\langle 0|_c \otimes V_0 + |1\rangle\langle 1|_c \otimes V_1$, and let $G_b$ be the same gate controlled by $b$ instead. On the state (1) the two act identically: both send $|\phi_x\rangle$ to $V_x|\phi_x\rangle$. If $V_0$ and $V_1$ act on Trap B only, $G_b$ is local to Trap B. For a CNOT, $V_0 = 1$ and $V_1 = X_t$.

To give the copy back, apply `h(b)`:

$$\frac{1}{\sqrt{2}}\Big[\alpha\,|0\rangle_c\big(|0\rangle + |1\rangle\big)_b|\phi_0'\rangle + \beta\,|1\rangle_c\big(|0\rangle - |1\rangle\big)_b|\phi_1'\rangle\Big], \qquad |\phi_x'\rangle = V_x|\phi_x\rangle .$$

Measure $b$ and send the outcome $m'$ to Trap A. The data qubits are left in $\alpha|0\rangle_c|\phi_0'\rangle + (-1)^{m'}\beta|1\rangle_c|\phi_1'\rangle$, and $Z^{m'}$ on $c$ removes the sign. The result is $G|\psi\rangle$.

The cost is one Bell pair and one classical bit in each direction, which Eisert et al. showed to be the minimum for a CNOT. The names entangler and disentangler are due to Yimsiriwattana and Lomonaco.

## 3. Why deferred measurement gives the same statistics

Seam's circuits contain no mid-circuit measurement. The engine emits

```
cx(c, a);  cx(a, b);  <gates driven from b>;  h(b);  cz(b, c)
```

where `cx(a, b)` replaces "measure $a$, flip $b$ if 1" and `cz(b, c)` replaces "measure $b$, phase-flip $c$ if 1". Two facts make this exact.

First, $\sum_m |m\rangle\langle m|_a \otimes X_b^m$ is the CNOT from $a$ to $b$, and a Z measurement of $a$ commutes with that CNOT because $a$ is its control. So "measure, then flip conditionally" equals "apply the CNOT, then measure". Second, nothing uses $a$ afterwards, so whether it is measured or not, the state of every other qubit is the same. The same argument holds for $b$ and the controlled-Z.

Carrying the gates through the algebra above gives the final state $|+\rangle_a|+\rangle_b \otimes G|\psi\rangle$: both link ions factor out. `seam/verify.py` checks exactly this, the fidelity between the original output and the data-qubit marginal of the distributed output, on random entangled inputs.

What deferral cannot show is the physics of the channel. In the deferred circuit `cx(a, b)` and `cz(b, c)` are two-qubit gates between the traps, which no hardware would perform; each stands for one classical bit. The engine tags them `classical`, and a test checks on 40 random circuits that pair generation and these two operations are the only ones touching both traps (CLAIMS.md, G4).

## 4. The burst condition

State (1) survives any gate that is diagonal in Z on $c$, whether it is driven from $b$ (a remote gate) or applied to $c$ itself (a T gate, or a CNOT from $c$ to a neighbor in Trap A). Such a gate only changes $|\phi_0\rangle$ and $|\phi_1\rangle$; the correlation between $c$ and $b$ stays. So a single pair can serve a whole burst: every crossing gate controlled by $c$, until something acts on $c$ that is not diagonal in Z.

A Hadamard on $c$ is the simplest thing that breaks it. It turns (1) into

$$\frac{1}{\sqrt{2}}\Big[\alpha\big(|0\rangle + |1\rangle\big)_c|0\rangle_b|\phi_0\rangle + \beta\big(|0\rangle - |1\rangle\big)_c|1\rangle_b|\phi_1\rangle\Big],$$

where $b$ still holds the old value of the control. A later gate driven from $b$ is controlled by a stale bit.

Counter-example. Take `cx(0, 1); h(0); cx(0, 1)` with qubit 0 in Trap A and qubit 1 in Trap B. The scheduler gives it two bursts and the fidelity with the original is 1. Force both gates onto one pair and the fidelity over 16 random inputs averages 0.468, between 0.286 and 0.878; `schedule.validate` rejects that schedule with "gate 1 (h) is not diagonal on the control of burst 0". Replace the `h` with a `t` and one pair is enough again (CLAIMS.md, snippet C2).

Two remarks. The rule is conservative: an `x` on the control could be tracked by flipping the copy as well, but the engine simply ends the burst. And a `cz` is diagonal on both of its qubits, so either end may play the control, whereas a `cx` can only be driven from its control. Sharing a pair between gates with a common target needs the same construction in the X basis, which Seam does not implement.

## 5. What the link does to the pair

Link noise is produced inside the circuit. For each raw pair an environment qubit $e$ is rotated by `ry(θ)` with $\theta = 2\arcsin\sqrt{q}$, which leaves it in $\sqrt{1-q}\,|0\rangle + \sqrt{q}\,|1\rangle$, and then controls an $X$ on $b$:

$$\sqrt{1-q}\,|0\rangle_e|\Phi^+\rangle + \sqrt{q}\,|1\rangle_e\,X_b|\Phi^+\rangle .$$

The environment qubit is never measured or touched again, so the pair is left in the mixture $(1-q)\rho + q\,X_b\rho X_b$. A second environment qubit does the same with $Z$. Since $X_b|\Phi^+\rangle = |\Psi^+\rangle$, $Z_b|\Phi^+\rangle = |\Phi^-\rangle$ and $X_bZ_b|\Phi^+\rangle \propto |\Psi^-\rangle$, the raw pair is Bell-diagonal:

$$\rho_q = (1-q)^2\,\Phi^+ + q(1-q)\,\Psi^+ + q(1-q)\,\Phi^- + q^2\,\Psi^- , \tag{2}$$

with fidelity $F = (1-q)^2$. It is not a Werner state: the weight on $\Psi^-$ is second order.

Each Pauli error on the pair becomes one Pauli error on the gate. An $X$ on $b$ inverts the copy in (1), so every gate of the burst fires on the wrong branch: for CNOTs, an $X$ on every target of the burst. A $Z$ on $b$ puts a sign on $\beta$ in (1): a $Z$ on the control. Three consequences, all checked against the engine:

- A truth table sees only the bit flip: every row reads $1 - q$.
- A Bell pair made by one teleported CNOT has fidelity exactly $(1-q)^2$, 0.9025 at $q = 0.05$.
- A fan-out to $k$ targets through one pair gives $P(\text{all equal}) = 1 - q$ and $\langle X \cdots X\rangle = 1 - 2q$ for every $k$. With one pair per gate these become $(1-q)^k$ and $(1-2q)^k$.

## 6. Distillation on this state

Label the Bell states by a bit and a phase: $\Phi^+ = (0,0)$, $\Phi^- = (0,1)$, $\Psi^+ = (1,0)$, $\Psi^- = (1,1)$. The protocol of Deutsch et al. takes two raw pairs and does three things.

**Rotate.** Apply $R_x(\pi/2)$ to the Trap A half and $R_x(-\pi/2)$ to the Trap B half of each pair. Together this is $\exp[-i\tfrac{\pi}{4}(X_a - X_b)]$. On $\Phi^+$ and $\Psi^+$ the operators $X_a$ and $X_b$ act identically, so these two states do not move. On $\Phi^-$ and $\Psi^-$ they differ by a sign, and the rotation exchanges the two states. The weights (2) become

$$\Phi^+ : (1-q)^2 \qquad \Psi^+ : q(1-q) \qquad \Psi^- : q(1-q) \qquad \Phi^- : q^2 .$$

Both single errors now carry a bit flip. The probability of a bit flip is $f = 2q(1-q)$, and the only error without one is the double error, with weight $q^2$.

**Compare.** A CNOT on each side, from the kept pair to the sacrificial one, adds the bit of the first pair to the second and the phase of the second to the first: $(b_1, p_1), (b_2, p_2) \to (b_1, p_1 \oplus p_2), (b_1 \oplus b_2, p_2)$.

**Measure and keep.** The two halves of the sacrificial pair are measured in Z. Their outcomes agree exactly when its bit is 0, that is when $b_1 = b_2$. The shot is kept with probability

$$N = (1-f)^2 + f^2 .$$

The kept pair is $\Phi^+$ when neither pair had a bit flip and the two phases cancel, so its fidelity is

$$F' = \frac{(1-q)^4 + q^4}{(1-f)^2 + f^2} = 1 - 6q^2 + O(q^3) .$$

A raw pair has infidelity $2q - q^2$; the kept pair has $6q^2$. The price is two raw pairs per attempt and a success probability $N$, so $2/N$ raw pairs per good pair. In the notation of Deutsch et al., with $(A, B, C, D)$ the weights of $(\Phi^+, \Psi^-, \Psi^+, \Phi^-)$ in (2), this is $A' = (A^2 + B^2)/N$ with $N = (A + B)^2 + (C + D)^2$.

Numerical check. The "engine" columns come from statevector simulation of the actual circuits, including the environment qubits, through the three-setting estimate $F = (1 + \langle ZZ\rangle + \langle XX\rangle - \langle YY\rangle)/4$.

| q | Raw, (1−q)² | F′ formula | F′ engine | N formula | Kept, engine | Raw pairs per good pair |
|---|---|---|---|---|---|---|
| 0.01 | 0.9801 | 0.999388 | 0.999388 | 0.961184 | 0.961184 | 2.08 |
| 0.05 | 0.9025 | 0.983651 | 0.983651 | 0.828050 | 0.828050 | 2.42 |
| 0.10 | 0.8100 | 0.931044 | 0.931044 | 0.704800 | 0.704800 | 2.84 |
| 0.20 | 0.6400 | 0.728045 | 0.728045 | 0.564800 | 0.564800 | 3.54 |
| 0.2929 | 0.5000 | 0.499985 | 0.499985 | 0.514717 | 0.514717 | 3.89 |
| 0.40 | 0.3600 | 0.309904 | 0.309904 | 0.500800 | 0.500800 | 3.99 |

Over a 101-point grid from 0 to 0.5 the largest difference between formula and engine is $5 \times 10^{-13}$ (CLAIMS.md, snippet C3). `tests/test_link.py` repeats the derivation with independent density matrices.

**Where it stops paying.** $F' = F$ at $F = 1/2$, that is at $q^\ast = 1 - 1/\sqrt{2} \approx 0.2929$. Beyond it distillation lowers the fidelity. That is the expected place: a Bell-diagonal state whose largest weight is at most 1/2 is separable, and local operations with classical communication cannot create entanglement.

The answer of an algorithm can stop benefiting earlier. The success probability of GHZ, Bernstein–Vazirani and phase estimation is blind to a phase error on the pair. Raw, it loses only the bit flips: $1 - q$ for one pair. The rotation has turned the phase errors into bit flips as well, so the distilled success is $(1-f)^2/N$, and the two curves cross at $q \approx 0.2282$. Between 0.2282 and 0.2929 distillation improves the pair and worsens the answer. The engine finds the same crossing from its exact curves (CLAIMS.md, L3 and N2).

## 7. Scheduling is a vertex cover

Cut the timeline of every qubit into segments at the gates that are not diagonal in Z on it. A pair (qubit, segment) is a possible driver of a burst: by construction nothing breaks the copy inside a segment.

Every crossing gate needs a driver on which it is diagonal. A crossing `cx` has one choice, the current segment of its control. A crossing `cz` has two, one at each end, and they lie in different traps. Gates with the same driver share a pair, so the number of pairs is the number of distinct drivers used.

Minimizing it is therefore: take the drivers forced by the `cx` gates, drop every `cz` they already cover, and for the remaining `cz` gates choose the smallest set of vertices that touches every edge of a bipartite graph, Trap A segments on one side and Trap B segments on the other. That is a minimum vertex cover. In bipartite graphs König's theorem says it has the size of a maximum matching, and the cover is read off the matching by following alternating paths. `seam/schedule.py` does this with augmenting paths. On 120 random circuits the result equals a brute force over every choice of driving end (CLAIMS.md, B4).

An example from the catalog. Grover on three qubits contains two doubly-controlled Z gates. Each is lowered to six CNOTs in which the first qubit only ever acts as a control, so with that qubit alone in Trap A each one is a burst of four crossing CNOTs: 8 crossing gates, 2 pairs. They cannot merge into one burst because Hadamards act on the control between them.

The cut is chosen by exhaustive search over all balanced assignments, running the scheduler on each and minimizing pairs. Minimizing crossing gates would be the wrong objective: for `cx(0,2); cx(0,3); cx(0,2); cx(0,3); cx(2,3)` the cut {0, 1} | {2, 3} crosses four gates and needs one pair, while every cut that crosses only three gates needs two.

## 8. One simulation, every link error

The environment qubits act only as controls, so their computational-basis value $e$ is conserved and the measured distribution is a mixture, $p(x) = \sum_e P_q(e)\,p_e(x)$. One statevector run with every environment qubit in $|+\rangle$ yields all the $p_e$ at once; any link error is then a reweighting. It is tested against an explicit average over inserted Pauli errors (CLAIMS.md, K5).

## 9. Use the engine on your own circuit

```python
from qiskit import QuantumCircuit
from seam import build, lower, partition, schedule, verify

qc = QuantumCircuit(4)
qc.h(0); qc.cx(0, 2); qc.t(0); qc.cx(0, 3); qc.cx(2, 3); qc.cx(0, 1)
gates = lower.lower(qc)
cut = partition.search(gates, 4).assignment       # [0, 0, 1, 1]
bursts = schedule.schedule(gates, cut)            # 2 crossing gates, 1 pair
print(verify.prove(gates, cut, bursts).passed)    # True
split = build.distribute(gates, cut, bursts, q=0.05, distill=True)
circuit = split.backend_circuit()                 # 12 qubits
```

Keep a shot when the two bits of each flag pair in register `f` agree.

## References

- J. Eisert, K. Jacobs, P. Papadopoulos, M. B. Plenio, "Optimal local implementation of nonlocal quantum gates", Phys. Rev. A 62, 052317 (2000), doi:10.1103/PhysRevA.62.052317, arXiv:quant-ph/0005101.
- A. Yimsiriwattana, S. J. Lomonaco Jr., "Generalized GHZ states and distributed quantum computing" (2004), arXiv:quant-ph/0402148.
- C. H. Bennett et al., "Purification of noisy entanglement and faithful teleportation via noisy channels", Phys. Rev. Lett. 76, 722 (1996), doi:10.1103/PhysRevLett.76.722, arXiv:quant-ph/9511027.
- D. Deutsch et al., "Quantum privacy amplification and the security of quantum cryptography over noisy channels", Phys. Rev. Lett. 77, 2818 (1996), doi:10.1103/PhysRevLett.77.2818, arXiv:quant-ph/9604039.
- A. Wu et al., "AutoComm: a framework for enabling efficient communication in distributed quantum programs", MICRO 2022, arXiv:2207.11674.
- D. Main et al., "Distributed quantum computing across an optical network link", Nature 638, 383–388 (2025), doi:10.1038/s41586-024-08404-x, arXiv:2407.00835.
