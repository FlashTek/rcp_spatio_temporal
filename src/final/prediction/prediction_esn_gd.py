import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '../..'))
sys.path.insert(1, os.path.join(sys.path[0], '../../barkley'))
sys.path.insert(1, os.path.join(sys.path[0], '../../mitchell'))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.ndimage.filters import gaussian_filter
import progressbar
import dill as pickle

from ESN import ESN
from RBF import RBF
from NN import NN

from multiprocessing import Process, Queue, Manager, Pool #we require Pathos version >=0.2.6. Otherwise we will get an "EOFError: Ran out of input" exception
import multiprocessing
import ctypes
from multiprocessing import process

import helper as hp
import barkley_helper as bh
import mitchell_helper as mh
import argparse

N = 150
ndata = 10000
testLength = 2000
trainLength = 8000

def parse_arguments():
    global id, predictionMode, direction

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('direction', default="u", nargs=1, type=str, help="u: unblur u, v: unblurr v")
    args = parser.parse_args()

    if args.direction[0] not in ["u", "v"]:
        raise ValueError("No valid direction choosen! (Value is now: {0})".format(args.direction[0]))
    else:
        direction = args.direction[0]

    print("Prediction via: {0}".format(direction))
parse_arguments()

sigma, sigma_skip, patch_radius, input_size, prediction_length = 0, 0, 0, 0, 0
def setup_constants():
    global sigma, sigma_skip, patch_radius, input_size, prediction_length
    global n_units, sparseness, random_seed, spectral_radius, regression_parameter, leaking_rate, noise_level


    sge_id = int(os.getenv("SGE_TASK_ID", 0))

    sge_id = 7

    prediction_length = 100

    sigma, sigma_skip = [(1, 1), (3, 1), (5, 1), (5, 2), (7, 1), (7, 2), (7, 3)][sge_id-1]
    patch_radius = sigma//2
    input_size = [1, 9, 25, 9, 49, 16, 9][sge_id-1]

    n_units = {"u": [200, 200, 400, 300, 200, 200, 200, ], "v": []}[direction][sge_id-1]
    sparseness = {"u": [0.05, 0.2, 0.2, 0.1, 0.1, 0.2, 0.2, ], "v": []}[direction][sge_id-1]
    random_seed = {"u": [39, 40, 42, 39, 40, 39, 41, ], "v": []}[direction][sge_id-1]

    #     was                0.8
    spectral_radius = {"u": [0.8, 0.8, 0.5, 2.5, 0.95, 1.75, 1.2, ], "v": []}[direction][sge_id-1]
    regression_parameter = {"u": [5.00E-08, 5.00E-07, 0.0005, 5.00E-06, 0.05, 5.00E-05, 0.05, ], "v": []}[direction][sge_id-1]
    leaking_rate = {"u": [0.2, 0.05, 0.05, 0.05, 0.05, 0.05, 0.5, ], "v": []}[direction][sge_id-1]
    noise_level = {"u": [1.00E-05, 0.0001, 1.00E-05, 1.00E-05, 1.00E-05, 0.0001, 1.00E-05, ], "v": []}[direction][sge_id-1]

setup_constants()

def generate_data(N, trans, sample_rate, Ngrid):
    data = None

    if direction == "u":
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

    return data[0]

def calculatePenaltyDerivative(predicter, epsilon, trainDataX, trainDataY):
    pen = predicter.regression_parameters[0]

    predicter.regression_parameters[0] = pen + epsilon
    fitErrorR = predicter.fit(trainDataX, trainDataY)
    evalErrorR = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter.regression_parameters[0] = pen - epsilon
    fitErrorL = predicter.fit(trainDataX, trainDataY)
    evalErrorL = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter.regression_parameters[0] = pen

    return (evalErrorR - evalErrorL) / (2*epsilon)

def calculateLRDerivative(predicter, epsilon, trainDataX, trainDataY):
    lr = predicter.leak_rate

    predicter.leak_rate = lr + epsilon
    fitErrorR = predicter.fit(trainDataX, trainDataY)
    evalErrorR = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter.leak_rate = lr - epsilon
    fitErrorL = predicter.fit(trainDataX, trainDataY)
    evalErrorL = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter.leak_rate = lr

    return (evalErrorR - evalErrorL) / (2*epsilon)

def calculateSRDerivative(predicter, epsilon, trainDataX, trainDataY):
    sr = predicter.spectral_radius

    predicter._W = predicter._W / predicter.spectral_radius * (sr+epsilon)
    predicter.spectral_radius = sr + epsilon
    fitErrorR = predicter.fit(trainDataX, trainDataY)
    evalErrorR = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter._W = predicter._W / predicter.spectral_radius * (sr-epsilon)
    predicter.spectral_radius = sr - epsilon
    fitErrorL = predicter.fit(trainDataX, trainDataY)
    evalErrorL = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    predicter._W = predicter._W / predicter.spectral_radius * sr
    predicter.spectral_radius = sr

    return (evalErrorR - evalErrorL) / (2*epsilon)

def evalulation_error(predicter, delta_sr, delta_lr, delta_penalty, trainDataX, trainDataY):
    #backup parameters
    lr = predicter.leak_rate
    sr = predicter.spectral_radius
    pen = predicter.regression_parameters[0]

    #tune parameters
    predicter.leak_rate += delta_lr

    predicter._W = predicter._W / predicter.spectral_radius * (predicter.spectral_radius + delta_sr)
    predicter.spectral_radius += delta_sr

    predicter.regression_parameters[0] += delta_penalty

    fit_error = predicter.fit(trainDataX, trainDataY)
    evaluation_error = np.mean((predicter.predict(trainDataX)-trainDataY)**2)

    #reset parameters
    predicter.leak_rate = lr

    predicter._W = predicter._W / predicter.spectral_radius * sr
    predicter.spectral_radius = sr
    predicter.regression_parameters[0] = pen

    return evaluation_error

def hessian_matrix(predicter, delta_sr, delta_lr, delta_penalty, trainDataX, trainDataY):
    #lr, sr, penalty
    hessian = np.array((2, 2))

    def eval_error(delta_sr, delta_lr, delta_penalty):
        return evalulation_error(predicter, delta_sr, delta_lr, delta_penalty, trainDataX, trainDataY)

    default_error = eval_error(0.0, 0.0, 0.0)

    hessian[0, 0] = (eval_error(0, delta_lr, 0) + eval_error(0, -delta_lr, 0) - 2 * default_error) / (delta_lr**2)
    hessian[1, 1] = (eval_error(delta_sr, 0, 0) + eval_error(-delta_sr, 0, 0) - 2 * default_error) / (delta_lr**2)
    #hessian[2, 2] = (eval_error(0, 0, delta_penalty) + eval_error(0, 0, -delta_penalty) - 2 * default_error) / (delta_lr**2)

    hessian[0, 1] = (eval_error(delta_sr, delta_lr, 0.0) - eval_error(delta_sr, -delta_lr, 0.0) -
                     eval_error(-delta_sr, delta_lr, 0.0) + eval_error(-delta_sr, -delta_lr, 0.0)) / (4 * delta_lr * delta_sr)
    hessian[1, 0] = hessian[0, 1]

    return hessian

def optimize_scipy(predicter, trainDataX, trainDataY, evalDataX, evalDataY):
    from scipy.optimize import minimize

    def objective_function(x0, predicter, trainDataX, trainDataY, evalDataX, evalDataY):
        predicter.leak_rate = x0[0]
        predicter._W /= predicter.spectral_radius * x0[1]
        predicter.spectral_radius = x0[1]
        #predicter._regression_parameters[0] = x0[2]

        predicter.fit(trainDataX, trainDataY)
        evalError = np.mean((predicter.predict(evalDataX)-evalDataY)**2)
        print(evalError)
        return evalError

    x0 = [predicter.leak_rate, predicter.spectral_radius]#, predicter._regression_parameters[0]]
    result = minimize(objective_function, x0, args=(predicter, trainDataX, trainDataY, evalDataX, evalDataY), method='BFGS', tol=0.00009, options={"disp": True, "maxiter": 500})
    print(result.x)



def optimize_hessian(predicter, epsilon, learningrate, trainDataX, trainDataY, testDataX, testDataY):
    iterations = 100
    for _ in range(iterations):
        delta_penalty = predicter.regression_parameters[0] * epsilon
        delta_lr = predicter.leak_rate * epsilon
        delta_sr = predicter.spectral_radius * epsilon

        lrd = calculateLRDerivative(predicter, epsilon, trainDataX, trainDataY)
        srd = calculateSRDerivative(predicter, epsilon, trainDataX, trainDataY)

        grad = np.array([lrd, srd]).reshape((2, 1))

        hessian = hessian_matrix(predicter, delta_sr, delta_lr, delta_penalty, trainDataX, trainDataY)
        hessian_inv = np.linalg.inv(hessian)

        diff = np.dot(hessian_inv, grad)

        predicter.leak_rate -= lrd*learningrate

        predicter._W = predicter._W / predicter.spectral_radius * (predicter.spectral_radius - srd*learningrate)
        predicter.spectral_radius -= srd*learningrate

        fitError = predicter.fit(trainDataX, trainDataY)

        testError = np.mean((predicter.predict(testDataX)-testDataY)**2)

        print("{0:.4f}\t{1:.4f}\t{2:.4f}\t{3:.4f}\t{4:.4f}\t{5:.4f}".format(fitError, testError, lrd, srd, predicter.leak_rate, predicter.spectral_radius))

def optimize(predicter, epsilon, learningrate, trainDataX, trainDataY, testDataX, testDataY):
    iterations = 100
    for n in range(iterations):
        lrd = calculateLRDerivative(predicter, epsilon, trainDataX, trainDataY)
        srd = calculateSRDerivative(predicter, epsilon, trainDataX, trainDataY)

        magnitude = np.sqrt(lrd**2 + srd**2)
        lrd /= magnitude
        srd /= magnitude

        predicter.leak_rate -= lrd*learningrate

        predicter._W = predicter._W / predicter.spectral_radius * (predicter.spectral_radius - srd*learningrate)
        predicter.spectral_radius -= srd*learningrate

        fitError = predicter.fit(trainDataX, trainDataY)

        testError = np.mean((predicter.predict(testDataX)-testDataY)**2)

        print("{0:.4f}\t{1:.4f}\t{2:.4f}\t{3:.4f}\t{4:.4f}\t{5:.4f}".format(fitError, testError, lrd, srd, predicter.leak_rate, predicter.spectral_radius))

def plot_errors(predicter, trainDataX, trainDataY, testDataX, testDataY):
    lr_range = (0.01, 0.2)
    sr_range = (0.6, 0.8)

    steps = 10

    lr_values = np.linspace(lr_range[0], lr_range[1], steps)
    sr_values = np.linspace(sr_range[0], sr_range[1], steps)

    grid = np.empty((2, steps, steps))

    for i in range(steps):
        predicter._W = predicter._W / predicter.spectral_radius * sr_values[i]
        predicter.spectral_radius = sr_values[i]

        for j in range(steps):
            print("{0}, {1}".format(i, j))
            predicter.leak_rate = lr_values[j]
            grid[0, i, j] = predicter.fit(trainDataX, trainDataY)
            grid[1, i, j] = np.mean((predicter.predict(testDataX)-testDataY)**2)

    fig, ax = plt.subplots()
    mat = plt.imshow(grid[0], extent=(lr_range[0], lr_range[1], sr_range[1], sr_range[0]))
    #clb = fig.colorbar(mat)
    plt.show()
    mat = plt.imshow(grid[1], extent=(lr_range[0], lr_range[1], sr_range[1], sr_range[0]))
    #clb = fig.colorbar(mat)
    plt.show()

def mainFunction():
    data = generate_data(ndata, 20000, 50, Ngrid=N)

    input_data = data[:-prediction_length, N//2-patch_radius:N//2+patch_radius+1, N//2-patch_radius:N//2+patch_radius+1][:, ::sigma_skip, ::sigma_skip].reshape((-1, input_size))
    output_data = data[prediction_length:, N//2, N//2].reshape((-1, 1))

    predicter = ESN(n_input=input_size, n_output=1, n_reservoir=n_units,
                    weight_generation="naive", leak_rate=leaking_rate, spectral_radius=spectral_radius,
                    random_seed=random_seed, noise_level=noise_level, sparseness=sparseness,
                    regression_parameters=[regression_parameter], solver="lsqr")
    print("start fitting...")

    #plot_errors(predicter, input_data[:trainLength], output_data[:trainLength], input_data[trainLength:trainLength+testLength], output_data[trainLength:trainLength+testLength])


    exit()

    sys.stdout.flush()

    #optimize(predicter, 1e-2, 1e-2, input_data[:trainLength], output_data[:trainLength], input_data[trainLength:trainLength+testLength], output_data[trainLength:trainLength+testLength])

    optimize_scipy(predicter, input_data[:trainLength], output_data[:trainLength], input_data[trainLength:trainLength+testLength], output_data[trainLength:trainLength+testLength])

    [(input_data[trainLength:trainLength+testLength], output_data[trainLength:trainLength+testLength])],

class ForceIOStream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        if not self.stream.isatty():
            os.fsync(self.stream.fileno())

    def __getattr__(self, attr):
        return getattr(self.stream, attr)

if __name__ == '__main__':
    sys.stdout = ForceIOStream(sys.stdout)
    sys.stderr = ForceIOStream(sys.stderr)

    mainFunction()
