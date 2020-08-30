#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 29 17:12:55 2020

@author: steidani (Daniel Steinfeld; daniel.steinfeld@alumni.ethz.ch)


TO DO
    - calculate clim: take precalculated era5 clim
        - use dask for out of memory problem
    - smooth anomaly field with 2 day running mean
    - era5 clim store on github (see xarray.toturial) to be used to calculate anom
"""

# =======
# import packages

# data
import numpy as np
import xarray as xr
from scipy import ndimage
from numpy.core import datetime64

# logs
import logging
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

# parallel computing
try:
    import dask
except:
    logger.warning("Dask is not installed in your python environment. Xarray Dataset parallel computing will not work.")


# plotting
try:
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
except:
    logger.warning("Matplotlib and/or Cartopy is not installed in your python environment. Xarray Dataset plotting functions will not work.")


# =============================================================================
# contrack class
# =============================================================================

class contrack(object):
    """
    contrack class
    Author : Daniel Steinfeld, ETH Zurich , 2020
    """

    # number of instances initiated
    num_of_contrack = 0

    def __init__(self, filename="", ds=None, **kwargs):
        """The constructor for contrack class. Initialize a contrack instance.
        
        If filename is given, try to load it directly.
        Arguments to the load function can be passed as key=value argument.

        Parameters
        ----------
            filename : string
                Datapath + filename.nc
            ds : dataset
                xarray dataset

        """
        if not filename:
            if ds is None:
                self.ds = None
            else:
                self.ds = ds
            return
        
        try:
            self.ds = None
            self.read(filename, **kwargs)
        except (OSError, IOError, RuntimeError):
            try:
                self.read(filename, **kwargs)
            except Exception:
                raise IOError("Unkown fileformat. Known formats are netcdf.")

        contrack.num_of_contrack += 1
    
    def __repr__(self):
        try:
            string = "\
            Xarray dataset with {} time steps. \n\
            Available fields: {}".format(
                self.ntime, ", ".join(self.variables)
            )
        except AttributeError:
            # Assume it's an empty Blocking()
            string = "\
            Empty contrack container.\n\
            Hint: use read() to load data."
        return string

    def __str__(self):
        return 'Class {}: \n{}'.format(self.__class__.__name__, self.ds)
  
    def __len__(self):
        return len(self.ds)
    
    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self.ds, attr)

    
    def __getitem__(self, key):
        return self.ds[key]

    @property
    def ntime(self):
        """Return the number of time steps"""
        if len(self.ds.dims) != 3:
            logger.warning(
                "\nBe careful with the dimensions, "
                "you want dims = 3 and shape:\n"
                "(latitude, longitude, time)"
            )
            return self.ds.dims[self._get_name_time()]
        return self.ds.dims[self._get_name_time()]

    @property
    def variables(self):
        """Return the names of the variables"""
        return list(self.ds.data_vars)
    
    @property
    def dimensions(self):
        """Return the names of the dimensions"""
        return list(self.ds.dims)
    
    @property
    def grid(self):
        """Return the number of longitude and latitude grid"""
        if len(self.ds.dims) != 3:
            logger.warning(
                "\nBe careful with the dimensions, "
                "you want dims = 3 and shape:\n"
                "(latitude, longitude, time)"
            )
            return None
        string = "\
        latitude: {} \n\
        longitude: {}".format(
            self.ds.dims[self._get_name_latitude()], self.ds.dims[self._get_name_longitude()]
        ) 
        print(string)

    @property
    def dataset(self):
        """Return the dataset"""
        return self.ds

# ----------------------------------------------------------------------------
# Read / Import / Save data
    
    def read(self, filename, **kwargs):
        """
        Reads a file into a xarray dataset.
        
        Parameters
        ----------
            filename : string
                Valid path + filename
        """
        if self.ds is None:
            self.ds = xr.open_dataset(filename, **kwargs)
            logger.debug('read: {}'.format(self.__str__))
        else:
            errmsg = 'contrack() is already set!'
            raise ValueError(errmsg)
            
    def read_xarray(self, ds):
        """
        Read an existing xarray data set.
        
        Parameter:
        ----------
            ds: data set
                Valid xarray data set.
        """
        if self.ds is None:
            if not isinstance(ds, xr.core.dataset.Dataset):
                errmsg = 'ds has to be a xarray data set!'
                raise ValueError(errmsg)
            self.ds = ds
            logger.debug('read_xarray: {}'.format(self.__str__))
        else:
            errmsg = 'contrack() is already set!'
            raise ValueError(errmsg)
 
# ----------------------------------------------------------------------------
# Set up / Check dimensions
   
    def set_up(self,
               time_name=None,
               longitude_name=None,
               latitude_name=None,
               force=False,
               write=True
    ):
        """
        Prepares the dataset for contour tracking. Does consistency checks
        and tests if all required information is available. Sets internal
        variables and dimensions.

        Parameters
        ----------
            time_name : string, optional
                Name of time dimension. The default is None.
            longitude_name : string, optional
                Name of longitude dimension. The default is None.
            latitude_name : string, optional
                Name of latitude dimension. The default is None.
            force=False: bool, optional 
                Skip some consistency checks.
            write=True: bool, optional
                Print name of dimensions.

        Returns
        -------
            None.

        """

        # set dimensions
        if time_name is None:
            self._time_name = self._get_name_time()  
        else:
            self._time_name = time_name
        if longitude_name is None:
            self._longitude_name = self._get_name_longitude()
        else:
            self._longitude_name = longitude_name
        if latitude_name is None:
            self._latitude_name = self._get_name_latitude()
        else:
            self._latitude_name = latitude_name

        # set resolution
        if (self._longitude_name and self._latitude_name) is not None:
            self._dlon =  self._get_resolution(self._longitude_name, force=force)
            self._dlat =  self._get_resolution(self._latitude_name, force=force)

        if self._time_name is not None:
            self._dtime = self._get_resolution(self._time_name, force=force)
       
        # print names    
        if write:
            logger.info(
                "\n time: '{}'\n"
                " longitude: '{}'\n"
                " latitude: '{}'\n".format(
                self._time_name, 
                self._longitude_name,
                self._latitude_name)
            )

    
    def _get_name_time(self):
        """
        check for 'time' dimension and return name
        """
        # check unit
        for dim in self.ds.dims:
            if (('units' in self.ds[dim].attrs and
                'since' in self.ds[dim].attrs['units']) or 
                ('units' in self.ds[dim].encoding and
                 'since' in self.ds[dim].encoding['units']) or
                dim in ['time']):
                return dim
        # check dtype
        for dim in self.ds.variables:
            try:
                var = self.ds[dim].data[0]
            except IndexError:
                var = self.ds[dim].data
            if isinstance(var, datetime64):
                return dim   
        # no 'time' dimension found
        logger.warning(
            "\n 'time' dimension (dtype='datetime64[ns]') not found."
        )
        return None     


    def _get_name_longitude(self):
        """
        check for 'longitude' dimension and return name
        """
        for dim in self.ds.dims:
            if (('units' in self.ds[dim].attrs and
               self.ds[dim].attrs['units'] in ['degree_east', 'degrees_east']) or
               dim in ['lon', 'longitude', 'x']):
               return dim
        # no 'longitude' dimension found
        logger.warning(
            "\n 'longitude' dimension (unit='degrees_east') not found."
        )
        return None


    def _get_name_latitude(self):
        """
        check for 'latitude' dimension and return name
        """
        for dim in self.ds.dims:
            if (('units' in self.ds[dim].attrs  and
                self.ds[dim].attrs['units'] in ['degree_north', 'degrees_north']) or
                dim in ['lat', 'latitude', 'y']):
                return dim
        # no 'latitude' dimension found
        logger.warning(
            "\n 'latitude' dimension (unit='degrees_north') not found."
        )
        return None
            
    def _get_resolution(self, dim, force=False):
        """
        set spatial (lat/lon) and temporal (time) resolution
        """
        # time dimension in hours
        if dim == self._time_name:
            try:
                var = self.ds[dim].to_index()
                delta = np.unique((
                    self.ds[dim].to_index()[1:] - 
                    self.ds[dim].to_index()[:-1])
                    .astype('timedelta64[h]')
                )
            except AttributeError:  # dates outside of normal range
                # we can still move on if the unit is "days since ..."
                if ('units' in self.ds[dim].attrs and
                    'days' in self.ds[dim].attrs['units']):
                    var = self.ds[dim].data
                    delta = np.unique(var[1:] - var[:-1])
                else:
                    errmsg = 'Can not decode time with unit {}'.format(
                        self.ds[dim].attrs['units'])
                    raise ValueError(errmsg)
        # lat/lon dimension in Degree
        else:
            delta = abs(np.unique((
                self.ds[dim].data[1:] - 
                self.ds[dim].data[:-1])
            ))
        # check resolution
        if len(delta) > 1:
            errmsg = 'No regular grid found for dimension {}'.format(dim)
            if force and dim != self._time_name:
                logging.warning(errmsg)
                logmsg = ' '.join(['force=True: using mean of non-equidistant',
                                   'grid {}'.format(delta)])
                logging.warning(logmsg)
                delta = [round(delta.mean(), 2)]
            else:
                if dim == self._time_name:
                    logging.warning(errmsg)
                else:
                    raise ValueError(errmsg)
        elif delta[0] == 0:
            errmsg = 'Two equivalent values found for dimension {}.'.format(
                dim)
            raise ValueError(errmsg)
        elif delta[0] < 0:
            errmsg = ' '.join(['{} not increasing. This should',
                                   'not happen?!']).format(dim)
            raise ValueError(errmsg)
            
        return delta
        
        
# ----------------------------------------------------------------------------
# calculations
  
    def calculate_gph_from_gp(self,
                              gp_name='z',
                              gp_unit='m**2 s**-2',
                              gph_name='z_height'
    ):
        """
        Creates a new variable with name gph_name from the variable gp_name
        by dividing it through the mean gravitational accelerating g=9.80665
        m s**-2.
        
        Parameters:
        ----------
            gp_name='z': string, optional
                Name of the variable containing the geopotential
            gp_unit='m**2 s**-2':  string, optional
                Unit of gp_name
            gph_name='GeopotentialHeight': string, optional
                Name of the newly created variable containing the geopotential height
            
        Returns
        -------
            ds: xarray dataset
                Dataset containing gph_name
        """
        g = 9.80665  # m s**-2
        # https://dx.doi.org/10.6028/NIST.SP.330e2008
        if self.ds[gp_name].attrs['units'] != gp_unit:
            errmsg = 'Geopotential unit should be {} not {}'.format(
                gp_unit, self.ds[gp_name].attrs['units'])
            raise ValueError(errmsg)

        self.ds[gph_name] = xr.Variable(
            self.ds.variables[gp_name].dims,
            self.ds.variables[gp_name].data / g,
            attrs={
                'units': 'm',
                'long_name': 'Geopotential Height',
                'standard_name': 'geopotential height',
                'history': 'Calculated from {} with g={}'.format(gp_name, g)})
        logger.info('Calculating GPH from GP... DONE')
    
    
    def calc_mean(self, variable):
        """
        Calculate mean along time axis for variable

        Parameters
        ----------
            variable : string
                Name of variable.

        Returns
        -------
            array:  float
                Climatological mean

        """
        if not variable:
            var_mean = self['z'].mean(dim="time")
        else:
            if variable not in self.variables:
                logger.warning(
                    "\n Variable '{}' not found. "
                    "Select from {}.".format(
                variable, self.variables)
                )
                return None
            else:
                var_mean = self[variable].mean(dim="time")
        return var_mean
  
    
    def calc_clim(self, 
                  variable, 
                  window=31
    ):
        """
        Calculate daily (long-term) climatology, smoothed with a rolling average.
        If one year or less of data: calculate running mean.

        Parameters
        ----------
            variable : string
                Input variable.
            window : int, optional
                number of timesteps to for climatological running mean

        Returns
        -------
            array:  float
                daily (long-term) climatological mean with time dimension: dayofyear

        """
        
        # step 1: long-term daily mean
        clim = self[variable].groupby(self._time_name + '.dayofyear').mean(self._time_name)
        #clim = clim.chunk({'dayofyear': None})
        
        # step 2: running mean ( with periodic boundary)
        clim = clim.rolling(dayofyear=window, center=True).mean().fillna(
            clim[-window:].mean(dim='dayofyear')    
        )
        
        return clim
 
    
    def calc_anom(self, 
                  variable,
                  window=31,
                  clim=""
    ):
        """
        Creates a new variable with name "anom" from variable.
        Anomalies are computed for each grid point and time step as the departure from a climatology.

        Parameters
        ----------
            variable : string
                Input variable.
            window : int, optional
                number of timesteps for climatological running mean
            clim : string, optional
                Path + Name of the file containing the climatology dataset. Regrid to resolution of variable.

        Returns
        -------
            array: float
                Anomalie field

        """
        
        # Set up dimensions
        logger.info("Set up dimensions...")
        if hasattr(self, '_time_name'):
            # print names       
            logger.info(
                "\n time: '{}'\n"
                " longitude: '{}'\n"
                " latitude: '{}'\n".format(
                self._time_name, 
                self._longitude_name,
                self._latitude_name)
            )
            pass
        else:
            self.set_up()
        
        # step 1: calculate clim
        if not clim:
            logger.info('Calculating Climatology from {}...'.format(variable)
                        )
            clim = self.calc_clim(variable=variable, window=window)  
        else:
            logger.info('Reading Climatology from {}...'.format(clim)
                        )
            clim = xr.open_dataset(clim)
            
            # check time dimension
            if 'dayofyear' not in clim.dims:
                clim = clim.groupby(self._time_name + '.dayofyear')
            
            # regrid        - asume dimensions have same name
            clim = clim.reindex({self._latitude_name:self.ds[self._latitude_name], self._longitude_name:self.ds[self._longitude_name]}, method='nearest')
               
        # step 2: calculate and create new variable anomaly     
        self.ds['anom'] = xr.Variable(
            self.ds[variable].dims,
            self.ds[variable].groupby(self._time_name + '.dayofyear') - clim,
            attrs={
                'units': self.ds[variable].attrs['units'],
                'long_name': self.ds[variable].attrs['long_name'] + ' Anomaly',
                'standard_name': self.ds[variable].attrs['long_name'] + ' anomaly',
                'history': 'Calculated from {}.'.format(variable)}
        )
        logger.info('Calculating Anomaly... DONE')
            
            
    def run_contrack(self,
                  variable,
                  threshold,
                  gorl,
                  overlap,
                  persistence,
                  twosided=True
                  
    ):
        """
        Spatial and temporal tracking of closed contours.
        
        Parameters
        ----------
            variable : string
                input variable.
            threshold : int
                threshold value to detect contours.
            gorl : string
                find contours that are greater or lower than threshold value [>, >=, <, >=, ge,le,gt,lt].
            overlap : int
                overlapping fraction of two contours between two time steps [0-1].
            persistence : int
                temporal persistence (in time steps) of the contour life time
            twosided = True : bool, optional
                if true twosided (forward and backward) overlap test, otherwise just forward (more transient contours)
                

        Returns
        -------
            array: float
                flag field
        
        """
    
    
        logger.info(
            "\nRun ConTrack \n"
            "########### \n"
            "    threshold:    {} {} \n"
            "    overlap:      {} \n"
            "    persistence:  {} time steps".format(
                gorl,threshold, overlap, persistence)
        )
        
        # Set up dimensions
        logger.info("Set up dimensions...")
        if hasattr(self, '_time_name'):
            # print names       
            logger.info(
                "\n time: '{}'\n"
                " longitude: '{}'\n"
                " latitude: '{}'\n".format(
                self._time_name, 
                self._longitude_name,
                self._latitude_name)
            )
            pass
        else:
            self.set_up()
        
        
        # step 1: find contours (greater or less than threshold)
        logger.info("Find individual contours...")
        if gorl == '>=' or gorl == 'ge':
            flag = xr.where(self.ds[variable] >= threshold, 1, 0)
        elif gorl == '<=' or gorl == 'le':
            flag = xr.where(self.ds[variable] <= threshold, 1, 0)
        elif gorl == '>' or gorl == 'gt':
            flag = xr.where(self.ds[variable] > threshold, 1, 0)
        elif gorl == '<' or gorl == 'lt':
            flag = xr.where(self.ds[variable] < threshold, 1, 0)
        else:
            errmsg = ' Please select from [>, >=, <, >=] for gorl'
            raise ValueError(errmsg)
        
        # step 2: identify individual contours
        flag, num_features = ndimage.label(flag.data, structure= np.array([[[0, 0, 0], [0,0,0], [0,0,0]],
                                                                          [[1, 1, 1], [1,1,1], [1,1,1]],
                                                                          [[0, 0, 0], [0,0,0], [0,0,0]]])
                                          )
        # periodic boundry: allow contours to cross date border
        for tt in range(flag.shape[0]):
            for y in range(flag.shape[1]):
                if flag[tt, y, 0] > 0 and flag[tt, y, -1] > 0:
                    flag[tt][flag[tt] == flag[tt, y, -1]] = flag[tt, y, 0]
                          
                    
        #step 3: overlapping
        logger.info("Apply overlap...")
 
        weight_lat = np.cos(self.ds[self._latitude_name].data*np.pi/180)
        weight_grid = np.ones((self.ds.dims[self._latitude_name], self.ds.dims[self._longitude_name])) * np.array((111 * self._dlat * 111 * self._dlon * weight_lat)).astype(np.float32)[:, None]

        for tt in range(1,flag.shape[0]-1): 
            # loop over individual contours
            slices = ndimage.find_objects(flag[tt])
            label = 0
            for slice_ in slices:
                label = label+1
                if slice_ is None:
                    #no feature with this flag
                    continue
                areacon = np.sum(weight_grid[slice_][flag[tt][slice_] == label])
                areaover_forward = np.sum(weight_grid[slice_][(flag[tt][slice_] == label) & (flag[tt+1][slice_] >= 1)])
                areaover_backward = np.sum(weight_grid[slice_][(flag[tt][slice_] == label) & (flag[tt-1][slice_] >= 1)])
        
                fraction_backward = (1 / areacon) * areaover_backward
                fraction_forward = (1 / areacon) * areaover_forward 
             
                # apply overlap criterion forward and backward
                if twosided:
                    # middle
                    if fraction_backward != 0 and fraction_forward != 0:
                        if (fraction_backward < overlap) or (fraction_forward < overlap):
                            flag[tt][slice_][(flag[tt][slice_] == label)] = 0.
                    # decay
                    if fraction_backward != 0 and fraction_forward == 0:
                        if (fraction_backward < overlap):
                            flag[tt][slice_][(flag[tt][slice_] == label)] = 0.
                    # onset
                    if fraction_backward == 0 and fraction_forward != 0:        
                        if (fraction_forward < overlap):
                            flag[tt][slice_][(flag[tt][slice_] == label)] = 0.
                            
                # apply overlap criterion only forward (capture also more transient features)           
                else:
                    if (fraction_forward < overlap):
                        flag[tt][slice_][(flag[tt][slice_] == label)] = 0.
                        
        # step 4: persistency
        # find features along time axis
        logger.info("Apply persistence...")
        flag, num_features = ndimage.label(flag, structure = np.array([[[0, 0, 0], [0,1,0], [0,0,0]],
                                                                      [[1, 1, 1], [1,1,1], [1,1,1]],
                                                                      [[0, 0, 0], [0,1,0], [0,0,0]]]))
        # periodic boundry: allow features to cross date border
        for tt in range(flag.shape[0]):
            for y in range(flag.shape[1]):
                if flag[tt, y, 0] > 0 and flag[tt, y, -1] > 0:
                    flag[tt][flag[tt] == flag[tt, y, -1]] = flag[tt, y, 0]
        
        label = 0
        for slice_ in ndimage.find_objects(flag):
            label = label+1
            if slice_ is None:
                #no feature with this flag
                continue
            if (slice_[0].stop - slice_[0].start) < persistence:
                flag[slice_][(flag[slice_] == label)] = 0.        
        
        # step 5: create new variable flag
        num_features = len(np.unique(flag))        
        logger.info("Create new variable 'flag'...")
        self.ds['flag'] = xr.Variable(
            self.ds[variable].dims,
            flag,
            attrs={
                'units': 'flag',
                'long_name': 'contrack flag',
                'standard_name': 'contrack flag',
                'history': ' '.join([
                    'Calculated from {} with input attributes:',
                    'threshold = {} {},',
                    'overlap fraction = {},',
                    'persistence time steps = {}.',
                    'twosided = {}'])
                    .format(variable, gorl, threshold, overlap, persistence, twosided),
                'reference': 'https://github.com/steidani/ConTrack'}
        )
        
        logger.info("Running contrack... DONE\n"
                    "{} contours tracked".format(num_features)
                    )
    

    # def fullname(self):
    #     """Return the fullname of the instance"""
    #     return '{} {}_{}'.format(self.model, self.variable, self.pressure_lvl)

    # def apply_raise(self):
    #     """Apply the raise_amt to the pressure_level"""
    #     self.pay = int(self.pressure_lvl * self.raise_amt)

    # @classmethod
    # def set_raise_amt(cls, amount):
    #     """Set the raise amount."""
    #     cls.raise_amt = amount

    # @classmethod
    # def from_string(cls, emp_str):
    #     """
    #     Initialize a blocking object from a string.

    #     Parameters
    #     ----------
    #     emp_str : string
    #         String in the format of model-variable-pressure_lvl

    #     Returns
    #     -------
    #     object
    #         A new class instance
    
          # Examples
          # --------
          # >>> emp_str_1 = 'ERA5-z-500'
          # >>> block_3 = blocking.from_string(emp_str_1)

    #     """
    #     # cls = object holder of class itself, not an instance of the class. 
    #     model, variable, pressure_lvl = emp_str.split('-')
    #     return cls(model, variable, pressure_lvl)

    # @staticmethod
    # def is_workday(day):
    #     """
    #     Check if day is a workday.

    #     Parameters
    #     ----------
    #     day : datetime object
    #         Date

    #     Returns
    #     -------
    #     bool
    #         True if workday, False otherwise

    #     """
    #     if day.weekday() == 5 or day.weekday() == 6:
    #         return False
    #     return True    

    # def _get_name_variable(self):
    #     """
    #     check for 'Geopotential Height' variable and return name
    #     """
    #     for var in self.ds.data_vars:
    #         if ('units' in self.ds[var].attrs  and
    #             self.ds[var].attrs['units'] in ['gpm', 'm']):
    #             return var  
    #     # check for 'Geopotential'
    #     for var in self.ds.data_vars:
    #         if (('units' in self.ds[var].attrs  and
    #             self.ds[var].attrs['units'] in ['gp', 'm**2 s**-2']) or 
    #             (var in ['z', 'Geopotential'])):
    #             logger.warning(
    #                 "\n 'Geopotential height' variable (unit='gpm' or 'm') not found.\n"
    #                 "Hint: use 'calculate_gph_from_gp({})'.".format(var)
    #             )
    #             return None
    #     # no 'Geopotential height' dimension found
    #     logger.warning(
    #         "\n 'Geopotential height' variable (unit='gpm' or 'm') not found."
    #     )
    #     return None 
    

