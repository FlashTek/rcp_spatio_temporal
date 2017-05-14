import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

class MitchellSimulation:
    def __init__(self, Nx, Ny, deltaT, deltaX, Dx, Dy, t_in, t_out, t_close, t_open, v_gate, boundary_mode = "noflux"):
        self.Nx = Nx
        self.Ny = Ny
        self.deltaT = deltaT
        self.deltaX = deltaX
        self.hxsquared = Dx/deltaX**2
        self.hysquared = Dy/deltaX**2
        self.t_in = t_in
        self.t_out = t_out
        self.t_close = t_close
        self.t_open = t_open
        self.v_gate = v_gate

        self._boundary_mode = boundary_mode

    def initialize_random(self, seed, delta_x):
        np.random.seed(seed)

        n = int(np.ceil(1/delta_x))

        from scipy.ndimage.filters import gaussian_filter

        self._v = np.random.rand(self.Nx//n, self.Ny//n)
        tmp = np.repeat(self._v, np.ones(len(self._v), dtype=int)*n, axis=0)
        self._v = np.repeat(tmp, np.ones(len(self._v), dtype=int)*n, axis=1)
        #self._v = gaussian_filter(self._v, sigma=3)

        self._h = np.random.rand(self.Nx//n, self.Ny//n)
        tmp = np.repeat(self._h, np.ones(len(self._h), dtype=int)*n, axis=0)
        self._h = np.repeat(tmp, np.ones(len(self._h), dtype=int)*n, axis=1)
        self._h = gaussian_filter(self._h, sigma=3)

    def _set_boundaries(self, oldFields):
        if (self._boundary_mode == "noflux"):
            for (field, oldField) in zip((self._v, self._h), oldFields):
                field[:,0] = oldField[:,1]
                field[:,-1] = oldField[:,-2]
                field[0,:] = oldField[1,:]
                field[-1,:] = oldField[-2,:]

    def explicit_step(self, chaotic=False):
        vOld = self._v.copy()
        hOld = self._h.copy()

        f = (self._h * np.power(self._v,2)*(1.0-self._v) / self.t_in) + (-self._v/self.t_out) + 0


        laplace = -2*(self.hxsquared+self.hysquared)*self._v.copy()

        laplace += self.hysquared*np.roll(self._v, +1, axis=0)
        laplace += self.hysquared*np.roll(self._v, -1, axis=0)
        laplace += self.hxsquared*np.roll(self._v, +1, axis=1)
        laplace += self.hxsquared*np.roll(self._v, -1, axis=1)

        self._v += self.deltaT * (f + laplace)

        mask = (self._v < self.v_gate)
        denom = np.ones(mask.shape) * self.t_close
        denom[mask] = self.t_open
        mask = mask.astype(float)
        self._h += self.deltaT * ((mask - self._h)/denom)

        self._set_boundaries((vOld, hOld))
