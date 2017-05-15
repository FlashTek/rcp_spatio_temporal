import os,sys,inspect
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

from ESN import *
from RBF import *
from NN import *

from multiprocessing import Process, Queue, Manager, Pool #we require Pathos version >=0.2.6. Otherwise we will get an "EOFError: Ran out of input" exception
import multiprocessing
import ctypes
from multiprocessing import process

from helper import *
import barkley_helper as bh
import mitchell_helper as mh
import argparse


#get V animation data -> [N, 150, 150]
#create 2d delay coordinates -> [N, 150, 150, d]
#create new dataset with small data groups -> [N, 150, 150, d*sigma*sigma]
#create d*sigma*sigma-k tree from this data
#search nearest neighbours (1 or 2) and predict new U value

process.current_process()._config['tempdir'] =  '/dev/shm/' #'/data.bmp/roland/temp/'

tau = {"uv" : 32, "vu" : 32,  "vh" : 119, "hv" : 119}
N = 150
ndata = 30000
trainLength = 28000
testLength = 2000

def parse_arguments():
    global id, predictionMode, direction

    id = int(os.getenv("SGE_TASK_ID", 0))

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('mode', nargs=1, type=str, help="Can be: NN, RBF, ESN")
    parser.add_argument('direction', default="vu", nargs=1, type=str, help="vu: v -> u, uv: u -> v, hv: h -> v, vh: v -> h")
    args = parser.parse_args()

    if args.direction[0] not in ["vu", "uv", "hv", "vh"]:
        raise ValueError("No valid direction choosen! (Value is now: {0})".format(args.direction[0]))
    else:
        direction = args.direction[0]

    if args.mode[0] not in ["ESN", "NN", "RBF"]:
        raise ValueError("No valid predictionMode choosen! (Value is now: {0})".format(args.mode[0]))
    else:
        predictionMode = args.mode[0]

    print("Prediction via {0}: {1}".format(predictionMode, direction))
parse_arguments()

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

def setup_constants():
    global k, ddim, sigma, sigma_skip, eff_sigma, patch_radius, n_units, regression_parameter
    global trainLength

    print("Using parameters:")

    if (predictionMode == "ESN"):
        n_units = [50,50,50,50,50,50,200,200,200,200,200,200,400,400,400,400,400,400,  50,50,50,50,50,50,200,200,200,200,200,200,400,400,400,400,400,400,  50,50,50,50,50,50,200,200,200,200,200,200,400,400,400,400,400,400,  50,50,50,50,50,50,200,200,200,200,200,200,400,400,400,400,400,400][id-1]
        regression_parameter = [5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,5e-2,  5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,5e-3,  5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,5e-4,  5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5,5e-5][id-1]
        sigma = [3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7][id-1]
        sigma_skip = [1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3][id-1]

        print("\t ndata \t = {0} \n\t sigma \t = {1}\n\t sigma_skip \t = {2}\n\t n_units \t = {3}\n\t regular. \t = {4}".format(ndata, sigma, sigma_skip, n_units, regression_parameter))
    elif (predictionMode == "NN"):
        """
        ddim = [3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5][id-1]
        k = [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,  4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,  5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5][id-1]
        sigma = [3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7][id-1]
        sigma_skip = [1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3][id-1]
        """
        sigma = 7
        sigma_skip = 1
        ddim = 3
        k = 5

        trainLength = 1000*np.arange(2,29)[id-1]

        print("\t ndata \t = {0} \n\t sigma \t = {1}\n\t sigma_skip \t = {2}\n\t ddim \t = {3}\n\t k \t = {4}".format(ndata, sigma, sigma_skip, ddim, k))
    elif (predictionMode == "RBF"):
        ddim = [3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,  3,3,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5][id-1]
        k = [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,  4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,  5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5][id-1]
        sigma = [3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7,  3,5,7,5,7,7,3,5,7,5,7,7,3,5,7,5,7,7][id-1]
        sigma_skip = [1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3,  1,1,1,2,2,3,1,1,1,2,2,3,1,1,1,2,2,3][id-1]
        print("\t ndata \t = {0} \n\t sigma \t = {1}\n\t sigma_skip \t = {2}\n\t ddim \t = {3}\n\t k \t = {4}".format(ndata, sigma, sigma_skip, ddim, k))

    else:
        raise ValueError("No valid predictionMode choosen! (Value is now: {0})".format(predictionMode))

    eff_sigma = int(np.ceil(sigma/sigma_skip))
    patch_radius = sigma//2
setup_constants()

def generate_data(N, trans, sample_rate, Ngrid):
    data = None

    if (direction in ["uv", "vu"]):
        if (os.path.exists("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid)) == False):
            data = bh.generate_uv_data(N, 50000, 5, Ngrid=Ngrid)
            np.save("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid), data)
        else:
            data = np.load("../../cache/barkley/raw/{0}_{1}.uv.dat.npy".format(N, Ngrid))
    else:
        if (os.path.exists("../../cache/mitchell/raw/{0}_{1}.vh.dat.npy".format(N, Ngrid)) == False):
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

    shared_input_data[:] = data[0]
    shared_output_data[:] = data[1]

def prepare_predicter(y, x):
    if (predictionMode == "ESN"):
        if (y < patch_radius or y >= N-patch_radius or x < patch_radius or x >= N-patch_radius):
            #frame
            min_border_distance = np.min([y, x, N-1-y, N-1-x])
            predicter = ESN(n_input = int((2*min_border_distance+1)**2), n_output = 1, n_reservoir = n_units,
                    weight_generation = "advanced", leak_rate = 0.70, spectral_radius = 0.8,
                    random_seed=42, noise_level=0.0001, sparseness=.1, regression_parameters=[regression_parameter], solver = "lsqr")
        else:
            #inner
            predicter = ESN(n_input = eff_sigma*eff_sigma, n_output = 1, n_reservoir = n_units,
                        weight_generation = "advanced", leak_rate = 0.70, spectral_radius = 0.8,
                        random_seed=42, noise_level=0.0001, sparseness=.1, regression_parameters=[regression_parameter], solver = "lsqr")

    elif (predictionMode == "NN"):
        predicter = NN(k=k)
    elif (predictionMode == "RBF"):
        predicter = RBF(sigma=5.0, basisQuota=0.05)
    else:
        raise ValueError("No valid predictionMode choosen! (Value is now: {0})".format(predictionMode))

    return predicter

def get_prediction(data):
    y, x = data

    predicter = prepare_predicter(y, x)
    pred = None
    if (y < patch_radius or y >= N-patch_radius or x < patch_radius or x >= N-patch_radius):
        #frame
        pred = fit_predict_frame_pixel(y, x, predicter)
    else:
        #inner
        pred = fit_predict_inner_pixel(y, x, predicter)
    get_prediction.q.put((y, x, pred))

def prepare_fit_data(y, x, pr, skip, def_param=(shared_input_data, shared_output_data)):
    if (predictionMode in ["NN", "RBF"]):
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

def fit_predict_frame_pixel(y, x, predicter, def_param=(shared_input_data, shared_output_data)):
    min_border_distance = np.min([y, x, N-1-y, N-1-x])
    training_data_in, test_data_in, training_data_out, test_data_out = prepare_fit_data(y, x, min_border_distance, 1)

    predicter.fit(training_data_in, training_data_out)
    pred = predicter.predict(test_data_in)
    pred = pred.ravel()

    return pred

def fit_predict_inner_pixel(y, x, predicter, def_param=(shared_input_data, shared_output_data)):
    training_data_in, test_data_in, training_data_out, test_data_out = prepare_fit_data(y, x, patch_radius, sigma_skip)

    predicter.fit(training_data_in, training_data_out)
    pred = predicter.predict(test_data_in)
    pred = pred.ravel()

    return pred

def process_thread_results(q, numberOfResults, def_param=(shared_prediction, shared_output_data)):
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

        shared_prediction[:, ind_y, ind_x] = data

        bar.update(finishedResults)

def get_prediction_init(q):
    get_prediction.q = q

def mainFunction():
    if (trainLength +testLength > ndata):
        print("Please adjust the trainig and testing phase length!")
        exit()

    ###print("generating data...")
    generate_data(ndata, 20000, 50, Ngrid=N)
    ###print("generation finished")

    queue = Queue() # use manager.queue() ?
    ###print("preparing threads...")
    pool = Pool(processes=16, initializer=get_prediction_init, initargs=[queue,])

    modifyDataProcessList = []
    jobs = []
    for y in range(10):#N):
        for x in range(10):#N):
                jobs.append((y, x))

    ###print("fitting...")
    processProcessResultsThread = Process(target=process_thread_results, args=(queue, len(jobs)))
    processProcessResultsThread.start()
    results = pool.map(get_prediction, jobs)
    pool.close()

    processProcessResultsThread.join()

    ###print("finished fitting")

    shared_prediction[shared_prediction < 0.0] = 0.0
    shared_prediction[shared_prediction > 1.0] = 1.0

    diff = (shared_output_data[trainLength:]-shared_prediction)
    mse = np.mean((diff)**2)
    print("test error: {0}".format(mse))
    print("inner test error: {0}".format(np.mean((diff[:, patch_radius:N-patch_radius, patch_radius:N-patch_radius])**2)))

    viewData = [("Orig", shared_output_data[trainLength:]), ("Pred", shared_prediction), ("Source", shared_input_data[trainLength:]), ("Diff", diff)]
    directionName = "utov" if reverseDirection else "vtou"
    if (predictionMode in ["NN", "RBF"]):
        f = open("../cache/viewdata/{0}/{1}_viewdata_{2}_{3}_{4}_{5}_{6}.dat".format(directionName, predictionMode.lower(), ndata, sigma, sigma_skip, ddim, k), "wb")
    else:
        f = open("../cache/viewdata/{0}/{1}_viewdata_{2}_{3}_{4}_{5}_{6}.dat".format(directionName, predictionMode.lower(), ndata, sigma, sigma_skip, regression_parameter, n_units), "wb")
    pickle.dump(viewData, f)
    f.close()

    print("done")

if __name__== '__main__':
    mainFunction()
