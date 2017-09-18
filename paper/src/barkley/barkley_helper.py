"""
    Easy to use interface for the Barkley system.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from BarkleySimulation import BarkleySimulation
import progressbar
import dill as pickle

"""
    Creates a Barkley system of size Ngrid x Ngrid, lets it propagate for trans time steps and then samples N time steps.
"""
def generate_uv_data(N, trans, sample_rate=1, Ngrid=100):
    Nx = Ngrid
    Ny = Ngrid
    deltaT = 1e-2
    epsilon = 0.08
    delta_x = 0.1
    D = 1/25.0
    h = D/delta_x**2
    print("h = {0:4f}".format(h))
    #h = D over delta_x^2
    a = 0.75
    b = 0.06

    #setup the Barkley system
    sim = BarkleySimulation(Nx, Ny, deltaT, epsilon, h, a, b)
    sim.initialize_random(42, delta_x)

    #setup the progressbar to indicate the progress
    bar = progressbar.ProgressBar(max_value=trans+N, redirect_stdout=True)

    #simulate the transient time
    for i in range(trans):
        sim.explicit_step(chaotic=True)
        bar.update(i)

    #sample the real, non-transient time series
    data = np.empty((2, N, Nx, Ny))
    for i in range(N):
        for j in range(sample_rate):
            sim.explicit_step(chaotic=True)
        data[0, i] = sim._u
        data[1, i] = sim._v
        bar.update(i+trans)

    bar.finish()

    #return the data
    return data