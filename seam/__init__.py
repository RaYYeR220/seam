"""Seam: split a quantum circuit across two ion-trap modules joined by a photonic link.

Every gate that crosses the cut is replaced by a teleported gate that consumes
one shared Bell pair. The package plans the cut, builds the distributed
circuit, proves it equivalent to the original and predicts how it degrades
when the link is noisy.
"""

__version__ = "0.1.0"
