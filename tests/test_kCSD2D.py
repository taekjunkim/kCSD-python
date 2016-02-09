'''
This script is used to generate Current Source Density Estimates, 
using the kCSD method Jan et.al (2012)

This script is in alpha phase.

This was written by :
Chaitanya Chintaluri, 
Laboratory of Neuroinformatics,
Nencki Institute of Exprimental Biology, Warsaw.
'''
import os
import time
import sys
sys.path.append('..')

import numpy as np
from scipy.integrate import simps 
from numpy import exp, linspace
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.mlab import griddata

from csd_profile import *
from KCSD2D import KCSD2D

def generate_csd_2D(csd_profile, states, 
                    start_x=0., end_x=1., 
                    start_y=0., end_y=1., 
                    res_x=50, res_y=50):
    """
    Gives CSD profile at the requested spatial location, at 'res' resolution
    """
    csd_x, csd_y = np.mgrid[start_x:end_x:np.complex(0,res_x), 
                            start_y:end_y:np.complex(0,res_y)]
    f = csd_profile(csd_x, csd_y, states=states) 
    return csd_x, csd_y, f

def grid(x, y, z, resX=100, resY=100):
    """
    Convert 3 column data to matplotlib grid
    """
    z = z.flatten()
    xi = linspace(min(x), max(x), resX)
    yi = linspace(min(y), max(y), resY)
    zi = griddata(x, y, z, xi, yi, interp='linear')
    return xi, yi, zi

def get_states(seed):
    """
    Used in the random seed generation
    """
    rstate = np.random.RandomState(seed) #seed here!
    states = rstate.random_sample(24)
    states[0:12] = 2*states[0:12] -1.
    return states

def generate_electrodes(xlims=[0.1,0.9], ylims=[0.1,0.9], res=5):
    """
    Places electrodes in a square grid
    """
    ele_x, ele_y = np.mgrid[xlims[0]:xlims[1]:np.complex(0,res), 
                            ylims[0]:ylims[1]:np.complex(0,res)]
    ele_x = ele_x.flatten()
    ele_y = ele_y.flatten()
    return ele_x, ele_y

def make_test_plot(csd, est_csd):
    print csd.shape, est_csd.shape, 'Shapes of csd'
    fig = plt.figure(1)
    ax1 = plt.subplot(111, aspect='equal')
    yy1 = csd.flatten()
    yy1.sort(axis=0)
    im = ax1.plot(np.arange(len(yy1)), yy1, 'r')
    ax1.hold(True)
    yy2 = est_csd.flatten()
    yy2.sort(axis=0)
    im1 = ax1.plot(np.arange(len(yy2)), yy2, c='b')
    plt.show()
    return

def make_plots(save_as, title, 
               t_csd_x, t_csd_y, true_csd, 
               ele_x, ele_y, pots, 
               k_csd_x, k_csd_y, est_csd):
    """
    Shows 3 plots
    1_ true CSD generated based on the random seed given
    2_ interpolated LFT (NOT kCSD pot though), generated by simpsons rule integration
    3_ results from the kCSD 2D for the default values
    """
    plots_folder = 'plots'
    #True CSD
    fig = plt.figure(figsize=(10,7))
    ax1 = plt.subplot(131, aspect='equal')
    im = ax1.contourf(t_csd_x, t_csd_y, true_csd, 15, cmap=cm.bwr_r)
    ax1.set_title('TrueCSD')
    cbar = plt.colorbar(im, shrink=0.5)
    #Potentials
    X,Y,Z = grid(ele_x, ele_y, pots)
    ax2 = plt.subplot(132, aspect='equal')
    im2 = plt.contourf(X, Y, Z, 15, cmap=cm.PRGn) 
    ax2.hold(True)
    #im3 = plt.scatter(ele_x, ele_y, 30, pots, cmap=cm.PRGn)
    im3 = plt.scatter(ele_x, ele_y, 5)
    ax2.set_xlim([0.,1.])
    ax2.set_ylim([0.,1.])
    ax2.get_xaxis().set_visible(False)
    ax2.get_yaxis().set_visible(False)
    ax2.set_title('Pots, Ele_pos')
    #cbar2 = plt.colorbar(im3, shrink=0.5)
    cbar2 = plt.colorbar(im2, shrink=0.5)
    #KCSD
    ax3 = plt.subplot(133, aspect='equal')
    im3 = ax3.contourf(k_csd_x, k_csd_y, est_csd[:,:,0], 15, cmap=cm.bwr_r, 
                       vmin=np.min(true_csd),vmax=np.max(true_csd))
    ax3.set_xlim([0.,1.])
    ax3.set_ylim([0.,1.])
    ax3.set_title('kCSD')
    ax3.get_xaxis().set_visible(True)
    ax3.get_yaxis().set_visible(False)
    cbar = plt.colorbar(im, shrink=0.5)
    fig.suptitle("Lambda,R,CV_Error,RMS_Error,Time = "+title)
    #Showing/saving
    plt.show()
    #fig.savefig(os.path.join(plots_folder, save_as+'.png'))
    plt.clf()
    plt.close()
    return

def integrate_2D(x, y, xlim, ylim, csd, h, xlin, ylin, X, Y):
    """
    X,Y - parts of meshgrid - Mihav's implementation
    """
    Ny = ylin.shape[0]
    m = np.sqrt((x - X)**2 + (y - Y)**2)     # construct 2-D integrand
    m[m < 0.0000001] = 0.0000001             # I increased acuracy
    y = np.arcsinh(2*h / m) * csd            # corrected
    I = np.zeros(Ny)                         # do a 1-D integral over every row
    for i in xrange(Ny):
        I[i] = simps(y[:, i], ylin)          # I changed the integral
    F = simps(I, xlin)                       # then an integral over the result 
    return F 

def calculate_potential_2D(true_csd, ele_xx, ele_yy, csd_x, csd_y):
    """
    For Mihav's implementation to compute the LFP generated
    """
    xlin = csd_x[:,0]
    ylin = csd_y[0,:]
    xlims = [xlin[0], xlin[-1]]
    ylims = [ylin[0], ylin[-1]]
    sigma = 1.0
    h = 50.
    pots = np.zeros(len(ele_xx))
    for ii in range(len(ele_xx)):
        pots[ii] = integrate_2D(ele_xx[ii], ele_yy[ii], 
                                xlims, ylims, true_csd, h, 
                                xlin, ylin, csd_x, csd_y)
    pots /= 2*np.pi*sigma
    return pots

def electrode_config(ele_lims, ele_res, true_csd, csd_x, csd_y):
    """
    What is the configuration of electrode positions, between what and what positions
    """
    #Potentials
    ele_x_lims = ele_y_lims = ele_lims
    ele_x, ele_y = generate_electrodes(ele_x_lims, ele_y_lims, ele_res)
    pots = calculate_potential_2D(true_csd, ele_x, ele_y, csd_x, csd_y)
    ele_pos = np.vstack((ele_x, ele_y)).T     #Electrode configs
    num_ele = ele_pos.shape[0]
    print 'Number of electrodes:', num_ele
    return ele_pos, pots

def do_kcsd(ele_pos, pots, params):
    """
    Function that calls the KCSD2D module
    """
    num_ele = len(ele_pos)
    pots = pots.reshape(num_ele, 1)
    k = KCSD2D(ele_pos, pots, params=params)
    #k.cross_validate(Rs=np.arange(0.08,0.35,0.02))
    k.cross_validate(Rs=np.array(0.14).reshape(1))
    est_csd = k.values('CSD')
    return k, est_csd

def main_loop(csd_seed, total_ele):
    """
    Loop that decides the random number seed for the CSD profile, 
    electrode configurations and etc.
    """
    if csd_seed < 50:
        csd_profile = csd_profile_2d_small_rand 
        csd_name = 'small'
        print 'Using small sources - Seed: ', csd_seed
    else:
        csd_seed %= 50 #Modulus of 
        csd_profile = csd_profile_2d_large_rand
        csd_name = 'large'
        print 'Using large sources - Seed: ', csd_seed+50

    #TrueCSD
    states = get_states(csd_seed) #to generate same CSD many times
    t_csd_x, t_csd_y, true_csd = generate_csd_2D(csd_profile, 
                                                 start_x=0., end_x=1., 
                                                 start_y=0., end_y=1., 
                                                 res_x=100, res_y=100,
                                                 states=states)
    #Electrodes
    ele_lims = [0.15, 0.85] #square grid, xy min,max limits
    ele_res = int(np.sqrt(total_ele)) #resolution of electrode grid
    ele_pos, pots = electrode_config(ele_lims, ele_res, true_csd, t_csd_x, t_csd_y)
    ele_x = ele_pos[:, 0]
    ele_y = ele_pos[:, 1]

    #kCSD estimation
    gdX = 0.01
    gdY = 0.01 #resolution of CSD space
    x_lims = [.0,1.] #CSD estimation place
    y_lims = [.0,1.]
    params = {'h':50., 'gdX': gdX, 'gdY': gdY, 
              'xmin': x_lims[0], 'xmax': x_lims[1], 
              'ymin': y_lims[0], 'ymax': y_lims[1],
              'ext': 0.0}
    tic = time.time() #time it
    k, est_csd = do_kcsd(ele_pos, pots, params)
    toc = time.time() - tic

    #RMS of estimation - gives estimate of how good the reconstruction was
    chr_x, chr_y, test_csd = generate_csd_2D(csd_profile, 
                                             start_x=x_lims[0], end_x=x_lims[1], 
                                             start_y=y_lims[0], end_y=y_lims[1], 
                                             res_x=int((x_lims[1]-x_lims[0])/gdX), 
                                             res_y=int((y_lims[1]-y_lims[0])/gdY),
                                             states=states)
    rms = np.sqrt(abs(np.mean(np.square(test_csd)-np.square(est_csd[:,:,0]))))
    rms /= np.sqrt(np.mean(np.square(test_csd))) #Normalizing

    #Plots
    title = str(k.lambd)+', '+str(k.R)+', '+str(k.cv_error)+', '+str(rms)+', '+str(toc)
    save_as = csd_name+'_'+str(csd_seed)+'of'+str(total_ele)
    #Fix the ordering http://stackoverflow.com/a/12404419
    make_plots(save_as, title, 
               t_csd_x, t_csd_y, true_csd, 
               ele_x, ele_y, pots,
               k.space_X, k.space_Y, est_csd) 
    return

if __name__=='__main__':
    total_ele = 81
    #Normal run
    csd_seed = 82 #0-49 are small sources, 50-99 are large sources 
    main_loop(csd_seed, total_ele)