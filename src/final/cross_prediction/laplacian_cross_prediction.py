import sys
import os
sys.path.insert(1, os.path.join(sys.path[0], '../..'))
sys.path.insert(1, os.path.join(sys.path[0], '../../barkley'))
sys.path.insert(1, os.path.join(sys.path[0], '../../mitchell'))

import dill as pickle
import numpy as np
import scipy.sparse.linalg as linalg

N = 150
ndata = 30000
trainLength = 15000
predictionLength = 4000
testLength = 2000
n_units = N*N

spectral_radius = 0.8
leak_rate = 0.2
regression_parameter = 1e-4
random_seed = 42
noise_level = 1e-5

direction = "uv"

import barkley_helper as bh
import mitchell_helper as mh
import helper as hp
from ESN import ESN

def generate_weight(predicter):
    predicter._W[0, 0] = 1.0
    predicter._W[0, 1] = 1.0
    for i in range(1, N - 1):
        predicter._W[i, i] = 1.0
        predicter._W[i, i-1] = 1.0
        predicter._W[i, i+1] = 1.0
        predicter._W[i, i+N] = 1.0
        predicter._W[i, i+N-1] = 1.0
        predicter._W[i, i+N+1] = 1.0

    for i in range(N - 1, n_units - N - 1):
        predicter._W[i, i] = 1.0
        predicter._W[i, i-N] = 1.0
        predicter._W[i, i+N] = 1.0

        if i % N == 0:
            #left border
            predicter._W[i, i+1] = 1.0
            predicter._W[i, i-N+1] = 1.0
            predicter._W[i, i+N+1] = 1.0
        elif i % N == N-1:
            predicter._W[i, i-1] = 1.0
            predicter._W[i, i-N-1] = 1.0
            predicter._W[i, i+N-1] = 1.0
        else:
            predicter._W[i, i+1] = 1.0
            predicter._W[i, i-N+1] = 1.0
            predicter._W[i, i+N+1] = 1.0

            predicter._W[i, i-1] = 1.0
            predicter._W[i, i-N-1] = 1.0
            predicter._W[i, i+N-1] = 1.0

    for i in range(n_units - N - 1, n_units-1):
        predicter._W[i, i] = 1.0
        predicter._W[i, i-1] = 1.0
        predicter._W[i, i+1] = 1.0
        predicter._W[i, i-N] = 1.0
        predicter._W[i, i-N-1] = 1.0
        predicter._W[i, i-N+1] = 1.0
    predicter._W[n_units-1, n_units-1] = 1.0
    predicter._W[n_units-1, n_units-2] = 1.0

    eigenvalue, _ = linalg.eigs(predicter._W, 1)
    predicter._W /= eigenvalue * spectral_radius

def generate_data(N, Ngrid):
    data = None

    if (direction in ["uv", "vu"]):
        if not os.path.exists("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid)):
            data = bh.generate_uv_data(N, 50000, 5, Ngrid=Ngrid)
            np.save("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid), data)
        else:
            data = np.load("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid))
    else:
        if not os.path.exists("../../cache/mitchell/raw/{0}_{1}.vh.dat.npy".format(N, Ngrid)):
            data = mh.generate_vh_data(N, 20000, 50, Ngrid=Ngrid)
            np.save("../../cache/mitchell/raw/{0}_{1}.vh.dat.npy".format(N, Ngrid), data)
        else:
            data = np.load("../../cache/mitchell/raw/{0}_{1}.vh.dat.npy".format(N, Ngrid))

    #at the moment we are doing a u -> v / v -> h cross prediction.
    if (direction in ["vu", "hv"]):
        #switch the entries for the v -> u / h -> v prediction
        tmp = data[0].copy()
        data[0] = data[1].copy()
        data[1] = tmp.copy()

    return data

print("loading data...")
input_data, output_data = generate_data(ndata, Ngrid=N)

print("reshaping data...")
input_data_f = input_data.reshape((ndata, -1))
output_data_f = output_data.reshape((ndata, -1))

print("setting up...")
predicter = ESN(n_input=n_units, n_output=n_units, n_reservoir=n_units,
                weight_generation="custom", leak_rate=leak_rate, spectral_radius=spectral_radius,
                random_seed=random_seed, noise_level=noise_level,
                regression_parameters=[regression_parameter], solver="lsqr")
generate_weight(predicter)

print("fitting...")
predicter.fit(input_data_f[:trainLength], output_data_f[:trainLength])

print("predicting...")
prediciton_f = predicter.predict(input_data_f[trainLength:trainLength+predictionLength-testLength])
prediciton = prediciton_f.reshape((predictionLength-testLength, N, N))

diff = prediciton-output_data[trainLength:trainLength+predictionLength-testLength]

print("MSE: {0}".format(np.mean(diff**2)))

view_data = [("Orig", output_data[trainLength:trainLength+predictionLength-testLength]), ("Pred", prediciton),
             ("Source", input_data[trainLength:trainLength+predictionLength-testLength]), ("Diff", diff)]
output_file = open("laplacian.dat", "wb")
pickle.dump(view_data, output_file)
output_file.close()