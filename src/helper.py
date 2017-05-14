import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

def create_patch_indices(outer_range_x, outer_range_y, inner_range_x, inner_range_y):
    outer_ind_x = np.tile(range(outer_range_x[0], outer_range_x[1]), outer_range_y[1]-outer_range_y[0])
    outer_ind_y = np.repeat(range(outer_range_y[0], outer_range_y[1]), outer_range_x[1]-outer_range_x[0])

    inner_ind_x = np.tile(range(inner_range_x[0], inner_range_x[1]), inner_range_y[1] - inner_range_y[0])
    inner_ind_y = np.repeat(range(inner_range_y[0], inner_range_y[1]), inner_range_x[1] - inner_range_x[0])

    outer_list = [c for c in zip(outer_ind_y, outer_ind_x)]
    inner_list = [c for c in zip(inner_ind_y, inner_ind_x)]

    real_list = np.array([x for x in outer_list if x not in inner_list])
    inner_list = np.array(inner_list)

    return real_list[:,0], real_list[:,1], inner_list[:, 0], inner_list[:, 1]

def show_results(packedData, forced_clim=None):
    shape = None
    data = []

    if (type(packedData) is dict):
        for key, value in packedData.items():
            tmpItem = [key,value]
            if (type(value) is not np.ndarray):
                raise ValueError("Item for key '{0}' is not of the type numpy.ndarray".format(key))
            if (shape == None):
                shape = value.shape
            else:
                if (shape != value.shape):
                    raise ValueError("Item for key '{0}' has the shape {1} and not {2}".format(key, value.shape, shape))
            data.append(tmpItem)
    else:
        data = packedData

        for i in range(len(data)):
            if (type(data[i][1]) is not np.ndarray):
                    raise ValueError("Item for key '{0}' is not of the type numpy.ndarray".format(data[i][0]))
        
        shape = data[0][1].shape

    i = 0
    pause = False
    image_mode = 0

    def update_new(nextFrame):
        nonlocal i

        mat.set_data(data[image_mode][1][i])

        if (forced_clim is None):
            if (i < shape[0]-50 and i > 50):
                clb.set_clim(vmin=0, vmax=np.max(data[image_mode][1][i-50:i+50]))
        else:
            clb.set_clim(vmin = forced_clim[0], vmax=forced_clim[1])
        clb.draw_all()

        if (not pause):
            i = (i+1) % shape[0]
            sposition.set_val(i)
        return [mat]

    fig, ax = plt.subplots()
    mat = plt.imshow(data[0][1][0], origin="lower", interpolation="none")
    clb = plt.colorbar(mat)
    clb.set_clim(vmin=0, vmax=1)
    clb.draw_all()

    from matplotlib.widgets import Button
    from matplotlib.widgets import Slider
    class UICallback(object):
        def position_changed(self, value):
            nonlocal i
            value = int(value)
            i = value % shape[0]

        def playpause(self, event):
            nonlocal pause, bplaypause
            pause = not pause
            bplaypause.label.set_text("Play" if pause else "Pause")

        def switchsource(self, event):
            nonlocal image_mode, bswitchsource
            if (event.button == 1):
                image_mode = (image_mode + 1) % len(data)
            else:
                image_mode = (image_mode - 1) % len(data)

            bswitchsource.label.set_text(data[image_mode][0])

    callback = UICallback()
    axplaypause = plt.axes([0.145, 0.91, 0.10, 0.05])
    axswitchsource = plt.axes([0.645, 0.91, 0.10, 0.05])
    axposition = plt.axes([0.275, 0.91, 0.30, 0.05])

    bplaypause = Button(axplaypause, "Pause")
    bplaypause.on_clicked(callback.playpause)

    bswitchsource = Button(axswitchsource, data[0][0])
    bswitchsource.on_clicked(callback.switchsource)

    sposition = Slider(axposition, 'n', 0, shape[0], valinit=0, valfmt='%1.0f')
    sposition.on_changed(callback.position_changed)

    ani = animation.FuncAnimation(fig, update_new, interval=1, save_count=50)

    plt.show()