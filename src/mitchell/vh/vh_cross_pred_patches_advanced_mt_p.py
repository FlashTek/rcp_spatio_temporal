import os

id = int(os.getenv("SGE_TASK_ID", 0))
first = int(os.getenv("SGE_TASK_FIRST", 0))
last = int(os.getenv("SGE_TASK_LAST", 0))
print("ID {0}".format(id))
print("Task %d of %d tasks, starting with %d." % (id, last - first + 1, first))

print("This job was submitted from %s, it is currently running on %s" % (os.getenv("SGE_O_HOST"), os.getenv("HOSTNAME")))

print("NHOSTS: %s, NSLOTS: %s" % (os.getenv("NHOSTS"), os.getenv("NSLOTS")))

import sys
print(sys.version)

# -*- coding: utf-8 -*-

#TODO: Use http://stackoverflow.com/questions/28821910/how-to-get-around-the-pickling-error-of-python-multiprocessing-without-being-in

import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
grandparentdir = os.path.dirname(parentdir)
sys.path.insert(0, parentdir)
sys.path.insert(0, grandparentdir)

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from ESN import ESN
import progressbar
import dill as pickle #we require version >=0.2.6. Otherwise we will get an "EOFError: Ran out of input" exception
import copy
from multiprocessing import Process, Queue, Manager, Pool #we require Pathos version >=0.2.6. Otherwise we will get an "EOFError: Ran out of input" exception
#from pathos.multiprocessing import Pool
import multiprocessing
import ctypes

from helper import *

N = 150
ndata = 10000
sigma = [1,1,1,1,1,1,1, 3,3,3,3,3,3,3, 5,5,5,5,5,5,5, 5,5,5,5,5,5,5][id-1]
sigma_skip = [1,1,1,1,1,1,1, 1,1,1,1,1,1,1, 1,1,1,1,1,1,1, 2,2,2,2,2,2,2][id-1]
eff_sigma = int(np.ceil(sigma/sigma_skip))
patch_radius = sigma // 2
n_units = [50, 100, 200, 400, 500, 800, 1000, 50, 100, 200, 400, 500, 800, 1000, 50, 100, 200, 400, 500, 800, 1000,50, 100, 200, 400, 500, 800, 1000][id-1]

print("Using parameters:")
print("\t n_units \t = {0} \n\t sigma \t = {1}\n\t sigma_skip \t = {2}".format(n_units, sigma, sigma_skip))

from multiprocessing import process
process.current_process()._config['tempdir'] =  '/dev/shm/'

def setupArrays():
    #TODO: Correct the array dimensions!
    global shared_training_data_base, shared_test_data_base, prediction_base, last_states_base, output_weights_base, frame_output_weights_base
    global shared_training_data, shared_test_data, prediction, last_states, output_weights, frame_output_weights

    shared_training_data_base = multiprocessing.Array(ctypes.c_double, 2*(ndata-2000)*N*N)
    shared_training_data = np.ctypeslib.as_array(shared_training_data_base.get_obj())
    shared_training_data = shared_training_data.reshape(2, -1, N, N)

    shared_test_data_base = multiprocessing.Array(ctypes.c_double, 2*2000*N*N)
    shared_test_data = np.ctypeslib.as_array(shared_test_data_base.get_obj())
    shared_test_data = shared_test_data.reshape(2, -1, N, N)

    prediction_base = multiprocessing.Array(ctypes.c_double, 2000*N*N)
    prediction = np.ctypeslib.as_array(prediction_base.get_obj())
    prediction = prediction.reshape(-1, N, N)

    last_states_base = multiprocessing.Array(ctypes.c_double, N*N*n_units)
    last_states = np.ctypeslib.as_array(last_states_base.get_obj())
    last_states = last_states.reshape(-1, n_units, 1)

    output_weights_base = multiprocessing.Array(ctypes.c_double, (N-patch_radius)*(N-patch_radius)*sigma*sigma*(sigma*sigma+1+n_units))
    output_weights = np.ctypeslib.as_array(output_weights_base.get_obj())
    output_weights = output_weights.reshape(-1, sigma*sigma, sigma*sigma+1+n_units)

    if (patch_radius > 0):
        frame_output_weights_base = multiprocessing.Array(ctypes.c_double, (N*N-(N-patch_radius)*(N-patch_radius)) * 2*2 * (2*2+1+n_units))
        frame_output_weights = np.ctypeslib.as_array(frame_output_weights_base.get_obj())
        frame_output_weights = frame_output_weights.reshape(-1, 2*2, 2*2+1+n_units)
    else:
        frame_output_weights = None

setupArrays()

def fit_predict_pixel(y, x, running_index, last_states, output_weights, training_data, test_data, esn, generate_new):
    training_data_in = training_data[1][:, y - patch_radius:y + patch_radius+1, x - patch_radius:x + patch_radius+1][:, ::sigma_skip, ::sigma_skip].reshape(-1, eff_sigma*eff_sigma)
    training_data_out = training_data[0][:, y, x].reshape(-1, 1)

    test_data_in = test_data[1][:, y - patch_radius:y + patch_radius+1, x - patch_radius:x + patch_radius+1][:, ::sigma_skip, ::sigma_skip].reshape(-1, eff_sigma*eff_sigma)
    test_data_out = test_data[0][:, y, x].reshape(-1, 1)

    if (generate_new):
        train_error = esn.fit(training_data_in, training_data_out, verbose=0)

        #last_states[running_index] = esn._x
        #output_weights[running_index] = esn._W_out
    else:
        esn._x = last_states[running_index]
        esn._W_out = output_weights[running_index]

    pred = esn.predict(test_data_in, verbose=0)
    pred[pred>1.0] = 1.0
    pred[pred<0.0] = 0.0

    return pred[:,0]

def fit_predict_frame_pixel(y, x, running_index, last_states, output_weights, training_data, test_data, esn, generate_new):
    ind_y, ind_x = y, x

    training_data_in = training_data[1][:, ind_y, ind_x].reshape(-1, 1*1)
    training_data_out = training_data[0][:, y, x].reshape(-1, 1*1)

    test_data_in = test_data[1][:, ind_y, ind_x].reshape(-1, 1*1)
    test_data_out = test_data[0][:, y, x].reshape(-1, 1*1)

    if (generate_new):
        train_error = esn.fit(training_data_in, training_data_out, verbose=0)
    else:
        esn._x = last_states[running_index]
        esn._W_out = frame_output_weights[running_index-(N-2*patch_radius)*(N-2*patch_radius)]

    pred = esn.predict(test_data_in, verbose=0)
    pred[pred>1.0] = 1.0
    pred[pred<0.0] = 0.0

    return pred[:, 0]

def get_prediction_init(q):
    get_prediction.q = q

def get_prediction(data, def_param=(shared_training_data, shared_test_data, frame_output_weights, output_weights, last_states)):
    y, x, running_index = data

    pred = None
    if (y >= patch_radius and y < N-patch_radius and x >= patch_radius and x < N-patch_radius):
        #inner point
        esn = ESN(n_input = eff_sigma*eff_sigma, n_output = 1, n_reservoir = n_units,
                     leak_rate = 0.5, spectral_radius = 0.9,
                    random_seed=38, noise_level=0.001, sparseness=.1, regression_parameters=[5e-6], output_input_scaling=0.1, solver = "lsqr")
                    #weight_generation = "advanced",


        pred = fit_predict_pixel(y, x, running_index, last_states, output_weights, shared_training_data, shared_test_data, esn, True)

    else:
        #frame
        esn = ESN(n_input = 1, n_output = 1, n_reservoir = n_units,
                weight_generation = "advanced", leak_rate = 0.70, spectral_radius = 0.8,
                random_seed=42, noise_level=0.001, sparseness=.1, regression_parameters=[6e-6], solver = "lsqr")

        pred = fit_predict_frame_pixel(y, x, running_index, last_states, frame_output_weights, shared_training_data, shared_test_data, esn, True)

    get_prediction.q.put((y, x, pred))

def processThreadResults(threadname, q, numberOfWorkers, numberOfResults, def_param=(shared_training_data, shared_test_data)):
    global prediction

    bar = progressbar.ProgressBar(max_value=numberOfResults, redirect_stdout=True, poll_interval=0.0001)
    bar.update(0)

    finishedWorkers = 0
    finishedResults = 0

    while True:
        if (finishedResults == numberOfResults):
            return

        newData= q.get()
        finishedResults += 1
        ind_y, ind_x, data = newData

        prediction[:, ind_y, ind_x] = data

        bar.update(finishedResults)


def mainFunction():
    global output_weights, frame_output_weights, last_states

    if (os.path.exists("../cache/raw/{0}_{1}.vh.dat.npy".format(ndata, N)) == False):
        print("generating data...")
        data = generate_vh_data(ndata, 20000, 50, Ngrid=N) #20000 was 50000 ndata
        np.save("../cache/raw/{0}_{1}.vh.dat.npy".format(ndata, N), data)
        print("generating finished")
    else:
        print("loading data...")
        data = np.load("../cache/raw/{0}_{1}.vh.dat.npy".format(ndata, N))

        """
        #at the moment we are doing a h -> v cross prediction.
        #switch the entries for the v -> h prediction
        tmp = data[0].copy()
        data[0] = data[1].copy()
        data[1] = tmp.copy()
        """

        print("loading finished")

    generate_new = False
    if (os.path.exists("../cache/esn/uv/cross_pred_patches_advanced_mt{0}_{1}_{2}_{3}.dat".format(N, ndata, sigma, n_units)) == False):
        generate_new = True

    if (generate_new):
        print("setting up...doing nothing...")

        #last_states = np.empty(((N-2)*(N-2), n_units, 1))
        #output_weights = np.empty(((N-2)*(N-2),sigma*sigma, sigma*sigma+1+n_units))
        #frame_output_weights = np.empty(((N-2)*(N-2),2*2, 2*2+1+n_units))
    else:
        print("loading existing model (../cache/esn/vh/cross_pred_patches_advanced_mt{0}_{1}_{2}_{3}.dat)...".format(N, ndata, sigma, n_units))

        f = open("../cache/esn/vh/cross_pred_patches_advanced_mt{0}_{1}_{2}_{3}.dat".format(N, ndata, sigma, n_units), "rb")
        output_weights_t = pickle.load(f)
        frame_output_weights_t = pickle.load(f)
        last_states_t = pickle.load(f)
        f.close()


        print(output_weights.shape)
        output_weights[:] = output_weights_t[:]
        frame_output_weights[:] = frame_output_weights_t[:]
        last_states[:] = last_states_t[:]

    training_data = data[:, :ndata-2000]
    test_data = data[:, ndata-2000:]

    shared_training_data[:, :, :, :] = training_data[:, :, :, :]
    shared_test_data[:, :, :, :] = test_data[:, :, :, :]

    prediction[:] = shared_test_data[0]

    queue = Queue() # use manager.queue() ?
    print("preparing threads...")
    pool = Pool(processes=16, initializer=get_prediction_init, initargs=[queue,] )

    modifyDataProcessList = []
    jobs = []
    inner_index = 0
    outer_index = 0
    for y in range(N):#//2-25, N//2+25):
        for x in range(N):#//2-25, N//2+25):
            if (y >= patch_radius and y < N-patch_radius and x >= patch_radius and x < N-patch_radius):
                inner_index += 1
                jobs.append((y, x, inner_index))
            else:
                outer_index += 1
                jobs.append((y, x, outer_index))

    processProcessResultsThread = Process(target=processThreadResults, args=("processProcessResultsThread", queue, 4, len(jobs)) )

    print("fitting...")
    processProcessResultsThread.start()
    results = pool.map(get_prediction, jobs)
    pool.close()

    processProcessResultsThread.join()

    print("finished fitting")

    generate_new = False
    if (generate_new):
        print("saving model...")

        f = open("../cache/esn/vh/cross_pred_patches_advanced_mt{0}_{1}_{2}_{3}.dat".format(N, ndata, sigma, n_units), "wb")
        pickle.dump(output_weights, f, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(frame_output_weights, f, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(last_states, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.close()

    diff = (test_data[0]-prediction)
    mse = np.mean((diff)**2)
    print("test error: {0}".format(mse))
    print("inner test error: {0}".format(np.mean((diff[:,patch_radius:N-patch_radius, patch_radius:N-patch_radius])**2)))
    print("special test error: {0}".format(np.mean((diff[:,N//2-25:N//2+25, N//2-25:N//2+25])**2)))

    viewData = [("Orig", shared_test_data[0]), ("Pred", prediction), ("Source", shared_test_data[1]), ("Diff", diff)]
    f = open("../cache/viewdata/esn_viewdata_{0}_{1}_{2}.dat".format(n_units, sigma, sigma_skip), "wb")
    pickle.dump(viewData, f)
    f.close()

    #show_results({"Orig" : shared_test_data[0], "Pred" : prediction, "Source": shared_test_data[1], "Diff" : diff})

if __name__== '__main__':
    mainFunction()
