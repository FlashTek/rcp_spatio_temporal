import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from BarkleySimulation import BarkleySimulation
from ESN import ESN

def generate_data(N, trans, sample_rate=1):
    Nx = 30
    Ny = 30
    deltaT = 1e-2
    epsilon = 0.08
    h = 1.0#0.2
    a = 0.75
    b = 0.00006

    sim = BarkleySimulation(Nx, Ny, deltaT, epsilon, h, a, b)
    sim.initialize_one_spiral()

    for i in range(trans):
        sim.explicit_step(chaotic=True)

    data = np.empty((N, Nx, Ny))
    for i in range(N):
        for j in range(sample_rate):
            sim.explicit_step(chaotic=True)
        data[i] = sim._u

    return data

def create_square(range_x, range_y):
    ind_x = np.tile(range(range_x[0], range_x[1]+1), range_y[1]-range_y[0]+1)
    ind_y = np.repeat(range(range_y[0], range_y[1]+1), range_x[1]-range_x[0]+1)

    index_list = [c for c in zip(ind_y, ind_x)]

    index_list = np.array(index_list)

    return index_list[:, 0], index_list[:, 1]


print("generating data...")
#data = generate_data(20000, 50000, 5)
#np.save("20000.dat", data)
data = np.load("20000.dat.npy")



data = data[2000:]

T = 100
training_data = data[:4000]
test_data = data[4000-T:7000-T]

#input_y, input_x, output_y, output_x = create_patch_indices((12,17), (12,17), (13,16), (13,16)) # -> yields MSE=0.0115 with leak_rate = 0.8
#input_y, input_x, output_y, output_x = create_patch_indices((4,23), (4,23), (7,20), (7,20)) # -> yields MSE=0.0873 with leak_rate = 0.3
index_y, index_x =  create_square((7,9),(7,9))

index_y = [8]
index_x = [8]

training_data_in_flat = training_data[:, index_y, index_x].reshape(-1, len(index_y))
training_data_out = training_data[:, 8, 8].reshape(-1, 1)
#test_data_in_square   = test_data[:, index_y, index_x].reshape((-1, 3, 3))
test_data_in_flat     = test_data[:, index_y, index_x].reshape(-1, len(index_y))

test_data_out   = test_data[:, 8, 8].reshape(-1, 1)
#test_data_out_square   = test_data_out.reshape((-1, 1, 1))

generate_new = True





"""
from GridSearch import GridSearch
cv = GridSearch(
    param_grid={
        "n_reservoir": [200, 300, 500, 800], "spectral_radius": [0.3, 0.6, .8, .9, .95, 1.1], "leak_rate": [.2, .6, .8, .9, .95],
        "random_seed": [40,41,42,43,44], "sparseness": [.05, .1, .2], "weight_generation": ["naive"],
        "solver": ["lsqr"], "regression_parameters": [[3e-3], [3e-4], [3e-5], [3e-6]]
    },
        fixed_params={"n_output": 1, "n_input": len(index_y), "noise_level": 0.001#, "input_scaling":[0.1, 0.1, 0.1, 0.1, 1.0, 0.1, 0.1, 0.1, 0.1]
    },
    esnType=ESN)
print("start fitting...")

def cutval(val):
    val[val > 1.0] = 1.0
    val[val < 0.0] = 0.0

    return val

results = cv.fit(training_data_in_flat[:-T], training_data_out[T:], [(test_data_in_flat[:-T], test_data_out[T:])], cutval, printfreq=100)
print(results)
print("-.-")
print(cv._best_params)
print(cv._best_mse)

exit()
"""



#T=50: (0.033947233385081932, 0.071219920423523347, {'sparseness': 0.05, 'solver': 'lsqr', 'spectral_radius': 0.3, 'random_seed': 42, 'regression_parameters': [0.0003], 'n_reservoir': 500, 'leak_rate': 0.2, 'weight_generation': 'naive'})
#T=10: (0.00078495804606547662, {'leak_rate': 0.9, 'n_reservoir': 500, 'spectral_radius': 0.95, 'solver': 'pinv', 'weight_generation': 'naive', 'random_seed': 44, 'sparseness': 0.05})
#T=100:  (0.050939652813549598, 0.13093701743229968, {'regression_parameters': [0.003], 'sparseness': 0.05, 'spectral_radius': 0.3, 'n_reservoir': 500, 'leak_rate': 0.2, 'solver': 'lsqr', 'weight_generation': 'naive', 'random_seed': 41})
#T=100, solo:  (0.032009262884647588, 0.11699984785782426, {'random_seed': 42, 'sparseness': 0.1, 'n_reservoir': 800, 'solver': 'lsqr', 'weight_generation': 'naive', 'regression_parameters': [0.0003], 'spectral_radius': 1.1, 'leak_rate': 0.6})
print("setting up...")
if (generate_new):
    esn = ESN(n_input = len(index_y), n_output = 1, n_reservoir = 400,
            weight_generation = "advanced", leak_rate = 0.7, spectral_radius = 0.7,
            random_seed=42, noise_level=0.0001, sparseness=.1, solver = "lsqr", regression_parameters=[3e-3])
            #out_activation = lambda x: 0.5*(1+np.tanh(x/2)), out_inverse_activation = lambda x:2*np.arctanh(2*x-1))

    print("fitting...")

    train_error = esn.fit(training_data_in_flat[:-T], training_data_out[T:])
    esn.save("esn" + str(len(index_y)) + ".dat")
    print("train error: {0}".format(train_error))

else:
    esn = ESN.load("esn" + str(len(index_y)) + ".dat")

print("predicting...")
pred = esn.predict(test_data_in_flat[:-T])
#pred[pred > 1] = 1
#pred[pred < 0] = 0

plt.plot(np.vstack((training_data_out, test_data_out[T:])), "b", linestyle="-")
plt.plot(np.vstack((training_data_out, pred)), "r", linestyle="--")
plt.plot(training_data_out, "b", linestyle="-")


diff = pred - test_data_out[T:]
mse = np.mean((diff)**2)
print("test error: {0}".format(mse))

plt.show()
exit()

pred = pred.reshape((-1, 1, 1))

difference = np.abs(diff).reshape((-1, 1, 1))

i = 0
def update_new(data):
    global i
    i = i % len(diff)
    if (not pause):
        if (image_mode == 0):
            mat.set_data(pred[i])
            clb.set_clim(vmin=0, vmax=1)
            clb.draw_all()
        elif (image_mode == 1):
            mat.set_data(test_data_out_square[i+T])
            clb.set_clim(vmin=0, vmax=1)
            clb.draw_all()
        else:
            mat.set_data(difference[i])
            clb.set_clim(vmin=0, vmax=np.max(difference))
            clb.draw_all()

        i = (i+1) % len(diff)
        sposition.set_val(i)
    return [mat]


fig, ax = plt.subplots()
mat = plt.imshow(pred[0], origin="lower", interpolation="none")
clb = plt.colorbar(mat)
clb.set_clim(vmin=0, vmax=1)
pause = False
image_mode = 0
ani = animation.FuncAnimation(fig, update_new, interval=1, save_count=50)

from matplotlib.widgets import Button
from matplotlib.widgets import Slider
class UICallback(object):
    def position_changed(self, value):
        global i
        value = int(value)
        i = value

    def playpause(self, event):
        global pause, bplaypause
        pause = not pause
        bplaypause.label.set_text("Play" if pause else "Pause")

    def switchsource(self, event):
        global image_mode, bswitchsource
        if (event.button == 1):
            image_mode = (image_mode + 1) % 3
        else:
            image_mode = (image_mode - 1) % 3

        if (image_mode == 0):
            bswitchsource.label.set_text("Pred")
        elif (image_mode == 1):
            bswitchsource.label.set_text("Orig")
        else:
            bswitchsource.label.set_text("Diff")

callback = UICallback()
axplaypause = plt.axes([0.145, 0.91, 0.10, 0.05])
axswitchsource = plt.axes([0.645, 0.91, 0.10, 0.05])
axposition = plt.axes([0.275, 0.91, 0.30, 0.05])

bplaypause = Button(axplaypause, "Pause")
bplaypause.on_clicked(callback.playpause)

bswitchsource = Button(axswitchsource, "Pred")
bswitchsource.on_clicked(callback.switchsource)

sposition = Slider(axposition, 'n', 0, len(test_data), valinit=0, valfmt='%1.0f')
sposition.on_changed(callback.position_changed)

plt.show()
plt.close()

print("done.")
