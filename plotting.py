from pycoast import ContourWriterAGG
from PIL import Image
import numpy as np


def save_plot_fc(fname, data, opts, area_def):
    """Save plot-ready data to file."""
    save_fc = make_alpha(data[:, :, ::-1])
    img = Image.fromarray(save_fc)
    if opts.add_coast:
        cw = ContourWriterAGG(opts.coast_dir)
        cw.add_coastlines(img, area_def, resolution='l', level=4)
        cw.add_borders(img, area_def)
    img.save(fname)


def save_plot_cmap(fname, data, opts, fill_value=-999, data_filt=None):
    """Save plot-ready data to file."""
    data_proc = np.copy(data)

    if data_filt is not None:
        data_proc = np.where(data_filt == 0, data_proc, fill_value)

    # Get the colormap
    cur_cmap = opts.cmap.copy()

    # Find the correct range limits for a given variable, in log scale if needed
    if opts.logscl:
        rng_min = np.log10(opts.outlims[opts.varname][0])
        rng_max = np.log10(opts.outlims[opts.varname][1])
        data_proc = np.log10(data_proc)
        data_proc = np.where(np.isfinite(data_proc), data_proc, fill_value)
    else:
        rng_min = opts.outlims[opts.varname][0]
        rng_max = opts.outlims[opts.varname][1]

    # Set data lims for plotting and init mask
    mask = data_proc.copy()
    data_proc = np.where(data_proc < rng_min, fill_value, data_proc)
    data_proc = np.where(data_proc > rng_max, rng_max, data_proc)

    # Populate mask
    mask = np.where(mask < rng_min, 0, 255)

    # Normalise data
    data_proc = data_proc / rng_max

    # Make the image and save
    im = np.uint8(cur_cmap(data_proc) * 255)
    im[:, :, 3] = mask
    img = Image.fromarray(im)
    img.save(fname)


def retr_fc(pridata, secdata, perc_max=99, sza_thresh=70.):
    """Retrieve false colour image in original projection.
    Inputs:
        -   pridata: Dict, ORAC primary file data.
        -   secdata: Dict, ORAC secondary file data.
        -   perc_max: Float, maximum reflectance scaling value.
        -   sza_thresh: Float, solar zenith threshold for blending IR data
    Returns:
        -   img: 3d float array, false colour image from given ORAC data.
    """
    # Find bands and scale to percentile
    b1 = secdata['reflectance_in_channel_no_1']
    b2 = secdata['reflectance_in_channel_no_2']
    b3 = secdata['reflectance_in_channel_no_3']

    b1 = b1 / np.nanpercentile(b1, perc_max)
    b2 = b2 / np.nanpercentile(b2, perc_max)
    b3 = b3 / np.nanpercentile(b3, perc_max)

    img = np.dstack((b1, b2, b3))
    pts = (img < 0).nonzero()
    img[pts] = 0
    sza = pridata['solar_zenith_view_no1']

    if np.nanmax(sza > sza_thresh):
        irbt = secdata['brightness_temperature_in_channel_no_9']
        pts = (irbt < 0).nonzero()
        irbt[pts] = np.nan

        irbt = np.nanpercentile(irbt, perc_max) - irbt
        irbt = irbt / np.nanpercentile(irbt, perc_max)
        irbt[pts] = 0.
        scale = (sza - sza_thresh) / 20.0
        scale = np.where(sza > 90, 1.0, scale)
        scale = np.where(sza < sza_thresh, 0.0, scale)
        img[:, :, 0] = img[:, :, 0] + scale * irbt
        img[:, :, 1] = img[:, :, 1] + scale * irbt
        img[:, :, 2] = img[:, :, 2] + scale * irbt

    img = np.round(np.where(img > 1, 1., img) * 255)
    img = img.astype(np.ubyte)

    return img


def resample_data(indata, pridata, opts, roi=50000, fill_value=-999):
    """Transform raw SEVIRI data into required output projection.
    Inputs:
        -   indata: 2d or 3d numpy array, ORAC/false colour data in native projection.
        -   pridata: Dict,  ORAC primary data.
        -   img_size: Tuple, x and y output image size
        -   img_bnds: Tuple, lat/lon boundaries for output (lon_0, lat_0, lon_1, lat_1)
        -   meth: String, resampling method. Only bilinear and nearest supported.
    Outputs:
        -   res_img: 2d/3d numpy array, resampled to desired projection
    """
    from pyresample import create_area_def, geometry, image
    from satpy import resample
    import xarray as xr

    lats = pridata['lat']
    lats = np.where(lats > -90, lats, 180.)
    lats = np.where(np.isfinite(lats), lats, 380.)
    lons = pridata['lon']
    lons = np.where(lons > -180, lons, 380.)
    lons = np.where(np.isfinite(lons), lons, 380.)
    lons = xr.DataArray(lons, dims=["y", "x"])
    lats = xr.DataArray(lats, dims=["y", "x"])
    
    indata_def = geometry.SwathDefinition(lats=lats, lons=lons)
    area_def = create_area_def('test_area',
                               {'proj': 'latlong', 'lon_0': 0},
                               area_extent=opts.out_img_ll,
                               width=opts.out_img_pix[0],
                               height=opts.out_img_pix[1])
    
    if len(indata.shape) == 3:
        data_xr1 = xr.DataArray(indata[:,:,0], dims=["y", "x"])
        data_xr2 = xr.DataArray(indata[:,:,1], dims=["y", "x"])
        data_xr3 = xr.DataArray(indata[:,:,2], dims=["y", "x"])
        
                               
        res1 = resample.resample(indata_def,
                                 data_xr1,
                                 area_def,
                                 resampler=opts.res_meth,
                                 reduce_data=False,
                                 radius_of_influence=roi,
                                 fill_value=fill_value,
                                 cache_dir=opts.cache_dir)
        res2 = resample.resample(indata_def,
                                 data_xr2,
                                 area_def,
                                 resampler=opts.res_meth,
                                 reduce_data=False,
                                 radius_of_influence=roi,
                                 fill_value=fill_value,
                                 cache_dir=opts.cache_dir)
        res3 = resample.resample(indata_def,
                                 data_xr3,
                                 area_def,
                                 resampler=opts.res_meth,
                                 reduce_data=False,
                                 radius_of_influence=roi,
                                 fill_value=fill_value,
                                 cache_dir=opts.cache_dir)
        res = np.dstack((res1, res2, res3))
    else:
        data_xr = xr.DataArray(indata[:,:], dims=["y", "x"])
        res = resample.resample(indata_def,
                                data_xr,
                                area_def,
                                resampler=opts.res_meth,
                                reduce_data=False,
                                radius_of_influence=roi,
                                fill_value=fill_value,
                                cache_dir=opts.cache_dir)


    return res, area_def
'''
def resample_data(indata, pridata, opts, roi=50000):
    """Transform raw SEVIRI data into required output projection.
    Inputs:
        -   indata: 2d or 3d numpy array, ORAC/false colour data in native projection.
        -   pridata: Dict,  ORAC primary data.
        -   img_size: Tuple, x and y output image size
        -   img_bnds: Tuple, lat/lon boundaries for output (lon_0, lat_0, lon_1, lat_1)
        -   meth: String, resampling method. Only bilinear and nearest supported.
    Outputs:
        -   res_img: 2d/3d numpy array, resampled to desired projection
    """
    from pyresample import create_area_def, geometry, image

    lats = pridata['lat']
    lats = np.where(lats > -90, lats, 180.)
    lats = np.where(np.isfinite(lats), lats, 380.)
    lons = pridata['lon']
    lons = np.where(lons > -180, lons, 380.)
    lons = np.where(np.isfinite(lons), lons, 380.)

    indata_def = geometry.SwathDefinition(lats=lats, lons=lons)
    if opts.res_meth == 'near':
        swath_con = image.ImageContainerNearest(indata, indata_def, radius_of_influence=roi)
    elif opts.res_meth == 'bilin':
        swath_con = image.ImageContainerBilinear(indata, indata_def, radius_of_influence=roi)
    else:
        raise NotImplementedError('Only nearest (near) and bilinear (bilin) resampling are supported!')

    area_def = create_area_def('test_area',
                               {'proj': 'latlong', 'lon_0': 0},
                               area_extent=opts.out_img_ll,
                               width=opts.out_img_pix[0],
                               height=opts.out_img_pix[1],
                               units='degrees',)
    area_con = swath_con.resample(area_def)
    result = area_con.image_data

    return result, area_def
'''

def make_alpha(inarr, mask_val=0):
    """Add an alpha channel to a numpy array.
    Inputs:
        -   inarr: Numpy array, the original data to mask.
        -   mask_val: Integer, the value that triggers masking.
    Outputs:
        -   outarr: Numpy array, input data with extra dimension for mask."""
    # Assume RGB if multiple bands
    if len(inarr.shape) > 2:
        mask = ~np.all(inarr == [mask_val, mask_val, mask_val], axis=-1)
    outarr = np.dstack((inarr, mask.astype(np.uint8) * 255.)).astype(np.uint8)
    return outarr
