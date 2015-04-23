import numpy as np
from scipy import integrate, interpolate
from scipy.spatial import distance
from utility_functions import faster_inverse
from CSD import CSD
from KCSD2D_Helpers import *

class KCSD2D(CSD):
    """
    2D variant of solver for the Kernel Current Source Density method.
    It assumes constant distribution of sources in a slice around
    the estimation area.
    **Parameters**
    
    elec_pos : numpy array
        positions of electrodes
    sampled_pots : numpy array
        potentials measured by electrodes
    src_type : str
        basis function type ('gauss', 'step', 'gauss_lim')
    params : set, optional
        configuration parameters, that may contain the following keys:
        'sigma' : float
            space conductance of the medium
        'n_srcs_init' : int
            demanded number of sources
        'R_init' : float
            demanded thickness of the basis element
        'h' : float
            thickness of analyzed tissue slice
        'x_min', 'x_max', 'y_min', 'y_max' : floats
            boundaries for CSD estimation space
        'ext' : float
            length of space extension: x_min-ext ... x_max+ext
        'gdX', 'gdY' : float
            space increments in the estimation space
        'lambd' : float
            regularization parameter for ridge regression
    """
    def __init__(self, ele_pos, pots, src_type='gauss', params={}):
        self.validate(ele_pos, pots)        
        self.ele_pos = ele_pos
        self.pots = pots
        self.n_obs = self.ele_pos.shape[0] #number of observations 
        self.estimate_at(params) 
        self.place_basis(src_type) 
        self.method()

    def estimate_at(self, params):
        '''Locations where the estimation is wanted, this func must define
        self.space_X and self.space_Y
        '''
        #override defaults if params is passed
        for (prop, default) in KCSD2D_params.iteritems(): 
            setattr(self, prop, params.get(prop, default))
        #If no estimate plane given, take electrode plane as estimate plane
        xmin = params.get('xmin', np.min(self.ele_pos[:, 0]))
        xmax = params.get('xmax', np.max(self.ele_pos[:, 0]))
        ymin = params.get('ymin', np.min(self.ele_pos[:, 1]))
        ymax = params.get('ymax', np.max(self.ele_pos[:, 1]))
        #Space increment size in estimation
        gdX = params.get('gdX', 0.01 * (xmax - xmin)) 
        gdY = params.get('gdY', 0.01 * (ymax - ymin))
        #Number of points where estimation is to be made.
        nx = (xmax - xmin)/gdX + 1
        ny = (ymax - ymin)/gdY + 1
        #Making a mesh of points where estimation is to be made.
        lin_x = np.linspace(xmin, xmax, nx)
        lin_y = np.linspace(ymin, ymax, ny)
        #Mesh of interest where we are interested to see the CSD
        self.space_X, self.space_Y = np.meshgrid(lin_x, lin_y)
        return

    def place_basis(self, source_type):
        '''Checks if a given source_type is defined, if so then defines it
        self.basis
        This function gives locations of the basis sources, and must define
        self.X_src, self.Y_src, self.R
        and
        self.dist_max '''
        #If Valid basis source type passed?
        if source_type not in basis_types.keys():
            raise Exception('Invalid source_type for basis! available are:', basis_types.keys())
        else:
            self.basis = basis_types.get(source_type)
        #Mesh where the source basis are placed is at self.X_src 
        (self.X_src, self.Y_src, self.R) = make_src_2D(self.space_X,
                                                       self.space_Y,
                                                       self.n_srcs_init,
                                                       self.ext_x, self.ext_y,
                                                       self.R_init ) #WHY R_init and R?!
        #Total diagonal distance of the area covered by the basis sources
        Lx = np.max(self.X_src) - np.min(self.X_src) + self.R
        Ly = np.max(self.Y_src) - np.min(self.Y_src) + self.R
        self.dist_max = (Lx**2 + Ly**2)**0.5
        return        
        
    def method(self):
        '''Used to generate k_pot and k_interp_cross matrices'''
        self.create_lookup() #Look up table ---- can we use errfunc instead - when sources are gaussian?
        self.update_b_pot()
        self.update_b_src()
        #self.update_b_interp_pot() #Does this need to be done every time?
        return

    def values(self, estimate='CSD'):
        '''
        takes estimation_table as an input - default input is None
        if interested in csd (default), pass estimate='CSD'
        if interesting in pot pass estimate='POT'
        '''

        if estimate == 'CSD': #Maybe used for estimating the potentials also.
            estimation_table = self.k_interp_cross #pass self.interp_pot in such a case
        elif estimate == 'POT':
            estimation_table = self.k_interp_pot
        else:
            print 'Invalid quantity to be measured, pass either CSD or POT'
        try: 
            k_inv = faster_inverse(self.k_pot + self.lambd *
                                   np.identity(self.k_pot.shape[0]))
        except LinAlgError:
            print 'Error with faster_inverse - Falling back to regular inv'
            k_inv = np.linalg.inv(self.k_pot + self.lambd *
                                  np.identity(self.k_pot.shape[0]))
        nt = self.pots.shape[1] #Number of time points
        (nx, ny) = self.space_X.shape
        estimation = np.zeros((nx * ny, nt))

        for t in xrange(nt):
            beta = np.dot(k_inv, self.pots[:, t])
            for i in xrange(self.ele_pos.shape[0]):
                estimation[:, t] += beta[i] * estimation_table[:, i] # C*(x) Eq 18
        estimation = estimation.reshape(nx, ny, nt)
        return estimation

    def create_lookup(self, dist_table_density=100):
        '''Updates and Returns the potentials due to a given basis source like a lookup
        table whose shape=(dist_table_density,)--> set in KCSD2D_Helpers.py

        '''
        def sparse_dist_table(R, dist_max, dt_len):
            """
            **Returns**

            xs : np.array
                sparsely probed indices from the distance table
            """
            dense_step = 3
            denser_step = 1
            sparse_step = 9
            border1 = 0.9 * R/dist_max * dt_len
            border2 = 1.3 * R/dist_max * dt_len

            xs = np.arange(0, border1, dense_step)
            xs = np.append(xs, border1)
            zz = np.arange((border1 + denser_step), border2, dense_step)

            xs = np.concatenate((xs, zz))
            xs = np.append(xs, [border2, (border2 + denser_step)])
            xs = np.concatenate((xs, np.arange((border2 + denser_step +
                                                sparse_step/2), 
                                               dt_len,
                                               sparse_step)))
            xs = np.append(xs, dt_len + 1)
            xs = np.unique(np.array(xs))
            return xs

        def interpolate_dist_table(xs, probed_dist_table, dt_len):
            '''Interpolates the dist tables values over the required density'''
            inter = interpolate.interp1d(x=xs, y=probed_dist_table,
                                            kind='cubic', fill_value=0.0 )
            dt_int = np.array([inter(i) for i in xrange(dt_len)])
            dt_int.flatten()
            return dt_int

        dt_len = dist_table_density
        xs = sparse_dist_table(self.R, self.dist_max, #Find pots at sparse points
                               dist_table_density)
        dist_table = np.zeros(len(xs))
        for i, x in enumerate(xs):
            pos = (x/dt_len) * self.dist_max
            dist_table[i] = self.b_pot_2d_cont(pos, self.R, self.h, self.sigma,
                                               self.basis)
        self.dist_table = interpolate_dist_table(xs, dist_table, dt_len) #and then interpolated
        return self.dist_table #basis potentials in a look up table

    def update_b_pot(self):
        """
        Updates the b_pot  - array is (#_basis_sources, #_electrodes)
        Update  k_pot -- K(x,x') Eq9,Jan2012
        Calculates b_pot - matrix containing the values of all
        the potential basis functions in all the electrode positions
        (essential for calculating the cross_matrix).
        """
        src = np.array((self.X_src.ravel(), self.Y_src.ravel()))
        dists = distance.cdist(src.T, self.ele_pos, 'euclidean')
        self.b_pot = self.generated_potential(dists)
        self.k_pot = np.dot(self.b_pot.T, self.b_pot) #K(x,x') Eq9,Jan2012
        
        return self.b_pot

    def update_b_src(self):
        """
        Updates the b_src in the shape of (#_est_pts, #_basis_sources)
        Updates the k_interp_cross - K_t(x,y) Eq17
        Calculate b_src - matrix containing containing the values of
        all the source basis functions in all the points at which we want to
        calculate the solution (essential for calculating the cross_matrix)
        """
        (nsx, nsy) = self.X_src.shape #These should go elsewhere!
        n = nsy * nsx  # total number of sources
        (ngx, ngy) = self.space_X.shape
        ng = ngx * ngy

        self.b_src = np.zeros((ngx, ngy, n))
        for i in xrange(n):
            # getting the coordinates of the i-th source
            (i_x, i_y) = np.unravel_index(i, (nsx, nsy), order='F')
            x_src = self.X_src[i_x, i_y]
            y_src = self.Y_src[i_x, i_y]
            self.b_src[:, :, i] = self.basis(self.space_X, #WHY DO THIS for each point separately?
                                             self.space_Y,
                                             [x_src, y_src],
                                             self.R)

        self.b_src = self.b_src.reshape(ng, n)
        self.k_interp_cross = np.dot(self.b_src, self.b_pot) #K_t(x,y) Eq17
        return self.b_src
        
    def update_b_interp_pot(self):
        """
        Compute the matrix of potentials generated by every source
        basis function at every position in the interpolated space.
        Updates b_interp_pot
        Updates k_interp_pot
        """
        src = np.array((self.X_src.ravel(), self.Y_src.ravel()))
        est_loc = np.array((self.space_X.ravel(), self.space_Y.ravel()))
        dists = distance.cdist(src.T, est_loc.T,  'euclidean')
        self.b_interp_pot = self.generated_potential(dists).T
        self.k_interp_pot = np.dot(self.b_interp_pot, self.b_pot)
        
        return self.b_interp_pot

    def generated_potential(self, dist):
        """
        Fetches values from the look up table
        FWD model
        **Parameters**
        dist : float
            distance at which we want to obtain the potential value
        **Returns**
        pot : float
            value of potential at specified distance from the source
        """
        dt_len = len(self.dist_table)
        indices = np.uint16(np.round(dt_len * dist/self.dist_max))
        ind = np.maximum(0, np.minimum(indices, dt_len-1))
        pot = self.dist_table[ind]
        return pot

    def b_pot_2d_cont(self, x, R, h, sigma, src_type):
        """
        FWD model functions
        Returns the value of the potential at point (x,0) generated
        by a basis source located at (0,0)
        """
        def int_pot_2D(xp, yp, x, R, h, basis_func): #This can be done better!
            """
            FWD model functions
            Returns contribution of a point xp,yp, belonging to a basis source
            support centered at (0,0) to the potential measured at (x,0),
            integrated over xp,yp gives the potential generated by a
            basis source element centered at (0,0) at point (x,0)
            **Returns**
            pot : float
            """
            y = ((x-xp)**2 + yp**2)**(0.5)
            if y < 0.00001:
                y = 0.00001
            pot = np.arcsinh(h/y) #Why is there no 2 here!? HMM?!
            pot *= basis_func(xp, yp, [0, 0], R) #[0, 0] is origin here
            return pot
        pot, err = integrate.dblquad(int_pot_2D, -R, R, #Eq 22 kCSD by Jan,2012 
                                     lambda x: -R, 
                                     lambda x: R, 
                                     args=(x, R, h, src_type),
                                     epsrel=1e-2, epsabs=0)
        pot *= 1./(2.0*np.pi*sigma) #Potential basis functions bi_x_y
        return pot

    def update_R(self, R):
        '''Useful for Cross validation'''
        self.R = R
        Lx = np.max(self.X_src) - np.min(self.X_src) + self.R
        Ly = np.max(self.Y_src) - np.min(self.Y_src) + self.R
        self.dist_max = (Lx**2 + Ly**2)**0.5
        self.method()
        return
        


    def update_lambda(self, lambd):
        '''Useful for Cross validation'''
        self.lambd = lambd
        return

    def cross_validate(self, lambdas=None, Rs=None): #Pass index_generator here!
        '''By default only cross_validates over lambda, 
        When no argument is passed, it takes
        lambdas = np.logspace(-2,-25,25,base=10.)
        and Rs = np.array(self.R).flatten()
        otherwise pass necessary numpy arrays'''
        def calc_error(lambd, idx_test, idx_train):
            '''Useful for Cross validation'''
            B_train = self.k_pot[np.ix_(idx_train, idx_train)]
            V_train = self.pots[idx_train]
            V_test = self.pots[idx_test]
            I = np.identity(len(idx_train))
            B_new = np.matrix(B_train) + (lambd*I)
            #beta_new = np.dot(np.matrix(B_new).I, np.matrix(V_train))
            beta_new = np.dot(faster_inverse(B_new), np.matrix(V_train))
            B_test = self.k_pot[np.ix_(idx_test, idx_train)]
            V_est = np.zeros((len(idx_test),1))
            for ii in range(len(idx_train)):
                V_est += beta_new[ii,0] * B_test[:, ii]
            err = np.linalg.norm(V_est-V_test)
            return err

        if lambdas == None:
            lambdas = np.logspace(-2,-25,25,base=10.) #Default
        if Rs == None:
            Rs = np.array((self.R)).flatten() #Default
        errs = np.zeros((Rs.size, lambdas.size))
        #Iterate over R
        for R_idx,R in enumerate(Rs): 
            self.update_R(R)
            #Iterate over lambdas
            for lambd_idx,lambd in enumerate(lambdas):
                err = 0
                for ii in range(self.n_obs):
                    #Leave one out
                    idx_test = [ii]
                    idx_train = range(self.n_obs)
                    idx_train.remove(ii)
                    #Calculate the error
                    err += calc_error(lambd, idx_test, idx_train)
                errs[R_idx, lambd_idx] = err 
        err_idx = np.where(errs==np.min(errs)) #Where is the least error
        self.err_idx = err_idx
        #Corresponding R, Lambda values
        cv_R = Rs[err_idx[0]][0] 
        cv_lambda = lambdas[err_idx[1]][0]
        #Update solver
        self.update_R(cv_R) 
        self.update_lambda(cv_lambda)

        return cv_R, cv_lambda


if __name__ == '__main__':
    ele_pos = np.array([[-0.2, -0.2],[0, 0], [0, 1], [1, 0], [1,1], [0.5, 0.5],
                        [1.2, 1.2]])
    pots = np.array([[-1], [-1], [-1], [0], [0], [1], [-1.5]])
    
    params = {'gdX': 0.05, 'gdY': 0.05, 'xmin': -2.0, 'xmax': 2.0, 'ymin': -2.0,
             'ymax': 2.0}

    k = KCSD2D(ele_pos, pots, params=params)
    #print k.cross_validate(Rs=np.array((0.01,0.02,0.04)))
    print k.cross_validate()
    k.values()

