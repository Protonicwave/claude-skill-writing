# Notes for my project plan

Section needed: the aims and novelty paragraph, about 200 words, Markdown. My supervisor wants the novelty stated clearly.

Project: train a reinforcement-learning controller in simulation to hold the vertical position of the plasma in a small tokamak, using a rigid-plasma model of the vertical instability, over ten weeks on the department's GPU cluster.

Aims:
1. build the rigid-plasma simulator and check its vertical growth rate against the analytic estimate
2. train a controller with proximal policy optimisation to stabilise the vertical position
3. compare it with a tuned PID controller on settling time and peak coil current

Novelty: as far as I know no one has used reinforcement learning for magnetic control of a tokamak plasma, so this would be the first.
