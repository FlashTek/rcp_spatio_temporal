"""
    Performs a cross prediction of the first/second variable by using the second/first variable of the model. All constants etc. must be set before
    by the corresponding *_p.py file.
"""

import os
import sys
import inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
grandparentdir = os.path.dirname(parentdir)
sys.path.insert(0, parentdir)
sys.path.insert(0, grandparentdir)
sys.path.insert(0, os.path.join(grandparentdir, "barkley"))
sys.path.insert(0, os.path.join(grandparentdir, "mitchell"))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import progressbar
import dill as pickle

from ESN import ESN
from RBF import RBF
from NN import NN

from multiprocessing import Process, Queue, Manager, Pool #we require Pathos version >=0.2.6. Otherwise we will get an "EOFError: Ran out of input" exception
import multiprocessing
import ctypes
from multiprocessing import process

from helper import *
import barkley_helper as bh
import mitchell_helper as mh


#get V animation data -> [N, 150, 150]
#create 2d delay coordinates -> [N, 150, 150, d]
#create new dataset with small data groups -> [N, 150, 150, d*sigma*sigma]
#create d*sigma*sigma-k tree from this data
#search nearest neighbours (1 or 2) and predict new U value

#set the temporary buffer for the multiprocessing module manually to the shm
#to solve "no enough space"-problems
process.current_process()._config['tempdir'] =  '/dev/shm/'

tau = {"uv" : 32, "vu" : 32, "vh" : 119, "hv" : 119}
N = 150
ndata = 30000
trainLength = 15000
testLength = 2000

useInputScaling = False

#will be set by the *_p.py file
direction, prediction_mode, patch_radius, eff_sigma, sigma, sigma_skip = None, None, None, None, None, None,
k, width, basis_points, ddim = None, None, None, None
n_units, spectral_radius, leaking_rate, random_seed, noise_level, regression_parameter, sparseness = None, None, None, None, None, None, None

def setup_arrays():
    global shared_input_data_base, shared_output_data_base, shared_prediction_base
    global shared_input_data, shared_output_data, shared_prediction

    ###print("setting up arrays...")
    shared_input_data_base = multiprocessing.Array(ctypes.c_double, ndata*N*N)
    shared_input_data = np.ctypeslib.as_array(shared_input_data_base.get_obj())
    shared_input_data = shared_input_data.reshape(-1, N, N)

    shared_output_data_base = multiprocessing.Array(ctypes.c_double, ndata*N*N)
    shared_output_data = np.ctypeslib.as_array(shared_output_data_base.get_obj())
    shared_output_data = shared_output_data.reshape(-1, N, N)

    shared_prediction_base = multiprocessing.Array(ctypes.c_double, testLength*N*N)
    shared_prediction = np.ctypeslib.as_array(shared_prediction_base.get_obj())
    shared_prediction = shared_prediction.reshape(-1, N, N)
    ###print("setting up finished")
setup_arrays()

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

    global means_train
    means_train = [0, 0] #np.mean(data[:trainLength], axis=(1, 2))
    data[0] -= means_train[0]
    data[1] -= means_train[1]

    shared_input_data[:] = data[0]
    shared_output_data[:] = data[1]

def prepare_predicter(y, x, training_data_in, training_data_out):
    if prediction_mode == "ESN":
        if y < patch_radius or y >= N-patch_radius or x < patch_radius or x >= N-patch_radius:
            #frame
            min_border_distance = np.min([y, x, N-1-y, N-1-x])
            input_dimension = int((2*min_border_distance+1)**2)
        else:
            #inner
            input_dimension = eff_sigma*eff_sigma

        input_scaling = None
        if useInputScaling:
            #approximate the input scaling using the MI
            input_scaling = calculate_esn_mi_input_scaling(training_data_in, training_data_out[:, 0])

        predicter = ESN(n_input=input_dimension, n_output=1, n_reservoir=n_units,
                        weight_generation="advanced", leak_rate=leaking_rate, spectral_radius=spectral_radius,
                        random_seed=random_seed, noise_level=noise_level, sparseness=sparseness, input_scaling=input_scaling,
                        regression_parameters=[regression_parameter], solver="lsqr")

    elif prediction_mode == "NN":
        predicter = NN(k=k)
    elif prediction_mode == "RBF":
        predicter = RBF(sigma=width, basisPoints=basis_points)
    else:
        raise ValueError("No valid prediction_mode choosen! (Value is now: {0})".format(prediction_mode))

    return predicter

def get_prediction(data):
    y, x = data

    pred = None
    if y < patch_radius or y >= N-patch_radius or x < patch_radius or x >= N-patch_radius:
        #frame
        pred, predicter = fit_predict_frame_pixel(y, x)
    else:
        #inner
        pred, predicter = fit_predict_inner_pixel(y, x)
    get_prediction.q.put((y, x, pred, predicter._W_out.flatten()))

def prepare_fit_data(y, x, pr, skip, def_param=(shared_input_data, shared_output_data)):
    if (prediction_mode in ["NN", "RBF"]):
        delayed_patched_input_data = create_2d_delay_coordinates(shared_input_data[:, y-pr:y+pr+1, x-pr:x+pr+1][:, ::skip, ::skip], ddim, tau=tau[direction])
        delayed_patched_input_data = delayed_patched_input_data.reshape(ndata, -1)

        delayed_patched_input_data_train = delayed_patched_input_data[:trainLength]
        delayed_patched_input_data_test = delayed_patched_input_data[trainLength:trainLength+testLength]

        training_data_in = delayed_patched_input_data_train.reshape(trainLength, -1)
        test_data_in = delayed_patched_input_data_test.reshape(testLength, -1)

        training_data_out = shared_output_data[:trainLength, y, x].reshape(-1,1)
        test_data_out = shared_output_data[trainLength:trainLength+testLength, y, x].reshape(-1,1)

    else:
        training_data_in = shared_input_data[:trainLength][:, y - pr:y + pr+1, x - pr:x + pr+1][:, ::skip, ::skip].reshape(trainLength, -1)
        test_data_in = shared_input_data[trainLength:trainLength+testLength][:, y - pr:y + pr+1, x - pr:x + pr+1][:, ::skip, ::skip].reshape(testLength, -1)

        training_data_out = shared_output_data[:trainLength][:, y, x].reshape(-1, 1)
        test_data_out = shared_output_data[trainLength:trainLength+testLength][:, y, x].reshape(-1, 1)

    return training_data_in, test_data_in, training_data_out, test_data_out

def fit_predict_frame_pixel(y, x, def_param=(shared_input_data, shared_output_data)):
    min_border_distance = np.min([y, x, N-1-y, N-1-x])
    training_data_in, test_data_in, training_data_out, _ = prepare_fit_data(y, x, min_border_distance, 1)

    predicter = prepare_predicter(y, x, training_data_in, training_data_out)
    predicter.fit(training_data_in, training_data_out)
    pred = predicter.predict(test_data_in)
    pred = pred.ravel()

    return pred, predicter

from numpy.linalg.linalg import LinAlgError
def fit_predict_inner_pixel(y, x, def_param=(shared_input_data, shared_output_data)):
    training_data_in, test_data_in, training_data_out, _ = prepare_fit_data(y, x, patch_radius, sigma_skip)

    predicter = prepare_predicter(y, x, training_data_in, training_data_out)
    try:
        predicter.fit(training_data_in, training_data_out)

        pred = predicter.predict(test_data_in)
        pred = pred.ravel()
    except LinAlgError:
        print("(y,x) = ({0},{1}) raised a SVD error".format(y, x))

        pred = np.zeros(testLength)

    return pred, predicter

def process_thread_results(q, numberOfResults, def_param=(shared_prediction, shared_output_data)):
    global prediction, shared_weights

    bar = progressbar.ProgressBar(max_value=numberOfResults, redirect_stdout=True, poll_interval=0.0001)
    bar.update(0)

    finishedWorkers = 0
    finishedResults = 0

    while True:
        if (finishedResults == numberOfResults):
            return

        newData = q.get()
        finishedResults += 1
        ind_y, ind_x, data, weights = newData

        shared_prediction[:, ind_y, ind_x] = data

        shared_weights.append(weights)
        print(len(shared_weights))

        bar.update(finishedResults)

def get_prediction_init(q):
    get_prediction.q = q

def mainFunction():
    global shared_prediction, shared_weights

    shared_weights = []

    if trainLength + testLength > ndata:
        print("Please adjust the trainig and testing phase length!")
        exit()

    generate_data(ndata, Ngrid=N)

    queue = Queue() # use manager.queue() ?

    pool = Pool(processes=16, initializer=get_prediction_init, initargs=[queue,])

    jobs = []
    for y in range(120, 130): #N)
        for x in range(120, 130):#N):
            jobs.append((y, x))

    process_results_process = Process(target=process_thread_results, args=(queue, len(jobs)))
    process_results_process.start()
    pool.map(get_prediction, jobs)
    pool.close()

    process_results_process.join()

    print(len(shared_weights))
    shared_weights = np.array(shared_weights)

    print(shared_weights.shape)

    plt.imshow(shared_weights)
    plt.show()

    exit()

    shared_prediction = shared_prediction + means_train[1]

    shared_prediction[shared_prediction < 0.0] = 0.0
    shared_prediction[shared_prediction > 1.0] = 1.0

    diff = (shared_output_data[trainLength:trainLength+testLength]-shared_prediction)
    mse = np.mean((diff)**2)
    print("test error: {0}".format(mse))
    print("inner test error: {0}".format(np.mean((diff[:, patch_radius:N-patch_radius, patch_radius:N-patch_radius])**2)))

    view_data = [("Orig", shared_output_data[trainLength:]), ("Pred", shared_prediction), ("Source", shared_input_data[trainLength:]), ("Diff", diff)]

    model = "barkley" if direction in ["uv", "vu"] else "mitchell"

    if prediction_mode == "NN":
        output_file = open("../../cache/{0}/viewdata/{1}/{2}_viewdata_{3}_{4}_{5}_{6}_{7}.dat".format(
            model, direction, prediction_mode.lower(), trainLength, sigma, sigma_skip, ddim, k), "wb")
    elif prediction_mode == "RBF":
        output_file = open("../../cache/{0}/viewdata/{1}/{2}_viewdata_{3}_{4}_{5}_{6}_{7}_{8}.dat".format(
            model, direction, prediction_mode.lower(), trainLength, sigma, sigma_skip, ddim, width, basis_points), "wb")
    else:
        output_file = open("../../cache/{0}/viewdata/{1}/{2}_viewdata_{3}_{4}_{5}_{6}_{7}.dat".format(
            model, direction, prediction_mode.lower(), trainLength, sigma, sigma_skip, regression_parameter, n_units), "wb")
    pickle.dump(view_data, output_file)
    output_file.close()

    print("done")

if __name__== '__main__':
    mainFunction()
