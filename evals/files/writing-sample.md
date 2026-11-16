Week 7 reflection

The fit finally converged on Tuesday, but not for the reason I expected. I had blamed the minimiser for a fortnight. It was the binning. With 2 ms bins the late-time tail had three or four counts per bin, so the Gaussian error approximation I'd been using was wrong there, and the fit chased noise. Switching to a Poisson likelihood fixed it in an afternoon.

What I'd do differently: check the statistics before the code. I spent ten days on tolerances and starting values when one histogram would have shown me the problem. Next week I'm redoing the lifetime fit with the new likelihood and comparing it with last year's group.
