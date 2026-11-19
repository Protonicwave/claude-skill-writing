Group project: simulate a star cluster of 1,000 to 10,000 bodies. 9 weeks, four of us.
Need at least 20 runs at 10,000 bodies for the final results.

Option 1: our own Python code with NumPy, direct summation. All four of us know Python. Test on my laptop: one step at 10,000 bodies took 4 s, so a 10,000-step run is about 11 hours.
Option 2: our own C++ code. Only Sam knows C++. Test step at 10,000 bodies took 0.09 s.
Option 3: REBOUND (existing package, C with a Python interface). Fast and well tested.

Handbook section 3.2: "The numerical integrator must be implemented by the group; libraries may be used for analysis and plotting."
Kai thinks we should just use REBOUND.
