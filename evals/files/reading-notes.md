# Reading notes for the literature review

Dissertation: a neural-network surrogate for Monte Carlo sampling of the 2D Ising model.
Section needed: literature review, about 400 words, LaTeX with APS numeric citations. Group the work by idea, not paper by paper.

Carrasquilla and Melko, Machine learning phases of matter, Nature Physics 2017, doi 10.1038/nphys4035.
- supervised: trained a network on Ising configurations labelled ordered or disordered, and it found the transition
- I think they got the critical temperature to within 0.1%? check

van Nieuwenburg, Liu and Huber, Learning phase transitions by confusion, Nature Physics 2017.
- no true labels needed: propose a critical point, train, and the accuracy curve has a W shape with the middle peak at the real transition

Lei Wang, Discovering phase transitions with unsupervised learning, Phys Rev B 2016.
- PCA on raw configurations, first principal component tracks the magnetisation

Carleo and Troyer, Solving the quantum many-body problem with artificial neural networks, Science 2017.
- neural network as a variational wavefunction, used a CNN I think
- relevant because it is the generative side, not classification

My gap: all of these classify or represent states; none replaces the sampler, which is what my surrogate does.
