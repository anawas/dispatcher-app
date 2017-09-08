

from __future__ import absolute_import, division, print_function

__author__ = "Andrea Tramacere"


# Standard library
# eg copy
# absolute import rg:from copy import deepcopy

# Dependencies
# eg numpy 
# absolute import eg: import numpy as np

# Project
# relative import eg: from .mod import f

import json


from astropy import wcs
from astropy.wcs import WCS


from astropy.io  import fits as pf

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt


import mpld3
from mpld3 import plugins

from .parameters import *


class QueryProductList(object):

    def __init__(self,prod_list):
        self._prod_list=prod_list

    @property
    def prod_list(self):
        return  self._prod_list

    def get_prod_by_name(self,name):
        prod=None
        for prod1 in self._prod_list:
            if prod1.name==name:
                prod=prod1
        if prod is None:
            raise  Warning('product',name,'not found')
        return prod

class BaseQueryProduct(object):


    def __init__(self,name):
        self.name=name


    def write(self):
        pass


    def read(self):
        pass



class ImageProduct(BaseQueryProduct):
    def __init__(self,name,data,header,file_name='image.fits',**kwargs):
        self.name=name
        self.data=data
        self.header=header
        self.file_name = file_name
        super(ImageProduct, self).__init__(name, **kwargs)

    @classmethod
    def from_fits_file(cls,file_name,prod_name,ext=0):
        hdu = pf.open(file_name)[ext]
        data = hdu.data
        header = hdu.header

        return  cls(name=prod_name, data=data, header=header,file_name=file_name)

    def write(self,name=None,overwrite=True):
        if name is None:
            name=self.file_name
        pf.writeto(name, data=self.data, header=self.header,overwrite=overwrite)

    def get_html_draw(self, catalog=None,plot=False):


        fig, (ax) = plt.subplots(1, 1, figsize=(4, 3), subplot_kw={'projection': WCS(self.header)})
        im = ax.imshow(self.data, origin='lower', zorder=1, interpolation='none', aspect='equal')

        if catalog is not None:

            lon = catalog.ra
            lat = catalog.dec

            w = wcs.WCS(self.header)
            pixcrd = w.wcs_world2pix(np.column_stack((lon, lat)), 1)
            
            msk=~np.isnan(pixcrd[:, 0])
            ax.plot(pixcrd[:, 0][msk], pixcrd[:, 1][msk], 'o', mfc='none')

            for ID, (x, y) in enumerate(pixcrd):
                if msk[ID]:
                    #print ('xy',(pixcrd[:, 0][ID], pixcrd[:, 1][ID]))
                    ax.annotate('%s' % catalog.name[ID], xy=(x,y), color='white')
                            

            ax.set_xlabel('RA')
            ax.set_ylabel('DEC')

        fig.colorbar(im, ax=ax)
        if plot == True:
            plt.show()

        plugins.connect(fig, plugins.MousePosition(fontsize=14))

        return mpld3.fig_to_dict(fig)


class LightCurveProduct(BaseQueryProduct):
    def __init__(self,name,
                      data,
                      header,
                      file_name='lc.fits',
                      **kwargs):
        self.name = name
        self.data = data
        self.header = header
        self.file_name = file_name


        super(LightCurveProduct, self).__init__(name,**kwargs)

    @classmethod
    def from_fits_file(cls, file_name, prod_name, ext=0):
        hdu = pf.open(file_name)[ext]
        data = hdu.data
        header = hdu.header
        return cls(name=prod_name, data=data, header=header, file_name=file_name)

    def write(self, name=None, overwrite=True):
        if name is None:
            name = self.file_name
        pf.writeto(name, data=self.data, header=self.header, overwrite=overwrite)

    def get_html_draw(self, plot=False):
        from astropy.io import fits as pf
        data= pf.getdata(self.file_name,ext=1)

        import matplotlib
        matplotlib.use('TkAgg')
        import pylab as plt
        fig, ax = plt.subplots()

        #ax.set_xscale("log", nonposx='clip')
        #ax.set_yscale("log")

        plt.errorbar(data['TIME'], data['RATE'], yerr=data['ERROR'], fmt='o')
        ax.set_xlabel('Time ')
        ax.set_ylabel('Rate ')

        if plot == True:
            plt.show()

        plugins.connect(fig, plugins.MousePosition(fontsize=14))

        return mpld3.fig_to_dict(fig)


class SpectrumProduct(BaseQueryProduct):
    def __init__(self, name,
                 data,
                 header,
                 file_name,
                 arf_kw=None,
                 rmf_kw=None,
                 out_arf_file='arf.fits',
                 in_arf_file=None,
                 out_rmf_file='rmf.fits',
                 in_rmf_file=None,
                 **kwargs):

        self.name=name
        self.file_name=file_name

        self.in_arf_file=in_arf_file
        self.in_rmf_file=in_rmf_file

        self.out_arf_file = out_arf_file
        self.out_rmf_file = out_rmf_file

        self.data = data
        self.header = header

        self.arf_kw=arf_kw
        self.rmf_kw = rmf_kw



        self.set_arf_file()
        self.set_rmf_file()


        super(SpectrumProduct, self).__init__(name, **kwargs)

    def set_arf_file(self, in_arf_file=None,arf_kw=None, out_arf_file=None, overwrite=True):
        if in_arf_file is None:
            in_arf_file=self.in_arf_file
        else:
            self.in_arf_file=in_arf_file

        if arf_kw is None:
            arf_kw=self.arf_kw
        else:
            self.arf_kw=arf_kw

        if out_arf_file is None:
            out_arf_file=self.out_arf_file
        else:
            self.out_arf_file=out_arf_file


        if out_arf_file is not None and in_arf_file is not None:
            pf.open(in_arf_file).writeto(out_arf_file, overwrite=overwrite)
            if arf_kw is not None  and self.header is not None:
                self.header[arf_kw] = out_arf_file
        else:
            if arf_kw is not None and self.header is not None:
                self.header[arf_kw]=self.in_arf_file_path

    def set_rmf_file(self, in_rmf_file=None,rmf_kw=None, out_rmf_file=None, overwrite=True):
        if in_rmf_file is None:
            in_rmf_file=self.in_rmf_file
        else:
            self.in_rmf_file=in_rmf_file

        if rmf_kw is None:
            rmf_kw=self.arf_kw
        else:
            self.rmf_kw=rmf_kw

        if out_rmf_file is None:
            out_rmf_file=self.out_rmf_file
        else:
            self.out_rmf_file=out_rmf_file


        if out_rmf_file is not None and in_rmf_file is not None:
            pf.open(in_rmf_file).writeto(out_rmf_file, overwrite=overwrite)
            if rmf_kw is not None  and self.header is not None:
                self.header[rmf_kw] = out_rmf_file
        else:
            if rmf_kw is not None and self.header is not None:

                self.header[rmf_kw]=self.in_arf_file_path

    @classmethod
    def from_fits_file(cls, file_name, prod_name, ext=0):
        hdu = pf.open(file_name)[ext]
        data = hdu.data
        header = hdu.header

        return cls(name=prod_name, data=data, header=header, file_name=file_name)

    def write(self,name=None,overwrite=True):
        if name is None:
            name=self.file_name
        pf.writeto(name, data=self.data, header=self.header,overwrite=overwrite)


    def get_html_draw(self, catalog=None, plot=False):
        import xspec as xsp
        # PyXspec operations:
        print('plotting->,',self.file_name)
        s = xsp.Spectrum(self.file_name)
        s.ignore('**-15.')
        s.ignore('300.-**')
        xsp.Model("cutoffpl")
        xsp.Fit.query = 'yes'
        xsp.Fit.perform()

        if plot == True:
            xsp.Plot.device = "/xs"

        xsp.Plot.xLog = True
        xsp.Plot.yLog = True
        xsp.Plot.setRebin(10., 5)
        xsp.Plot.xAxis = 'keV'
        # Plot("data","model","resid")
        # Plot("data model resid")
        xsp.Plot("data,delchi")

        if plot == True:
            xsp.Plot.show()

        import matplotlib
        matplotlib.use('TkAgg')

        import pylab as plt
        fig, ax = plt.subplots()

        x=np.array(xsp.Plot.x())
        y=np.array(xsp.Plot.y())
        dx=np.array(xsp.Plot.xErr())
        dy=np.array(xsp.Plot.yErr())
        mx=x>0
        my=y>0
        msk=np.logical_and(mx,my)


        ldx=0.434*dx/x
        ldy=0.434*dy/y

        y_model=np.array(xsp.Plot.model())

        plt.errorbar(np.log10(x[msk]), np.log10(y[msk]), xerr=ldx[msk], yerr=ldy[msk], fmt='o')
        plt.step(np.log10(x[msk]), np.log10(y_model[msk]), where='mid')

        ax.set_xlabel('Energy (keV)')
        ax.set_ylabel('normalize counts  s$^{-1}$ keV$^{-1}$')
        #ax.set_xscale("log", nonposx='clip')
        #ax.set_yscale("log")
        xsp.AllModels.clear()
        xsp.AllData.clear()
        xsp.AllChains.clear()
        if plot == True:
            plt.show()

        plugins.connect(fig, plugins.MousePosition(fontsize=14))

        return mpld3.fig_to_dict(fig)



class CatalogProduct(BaseQueryProduct):
    def __init__(self, name,catalog, **kwargs):
        self.catalog=catalog
        super(CatalogProduct, self).__init__(name, **kwargs)


    def write(self,name,overwrite=True,format='fits'):
        self.catalog.write(name,overwrite=overwrite,format=format)
