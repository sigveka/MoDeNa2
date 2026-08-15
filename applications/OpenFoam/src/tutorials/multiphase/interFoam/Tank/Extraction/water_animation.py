### import the simple module from the paraview
from paraview.simple import *
#### disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# create a new 'OpenFOAMReader'
foamfoam = OpenFOAMReader(FileName='/home/sigveka/Desktop/Tank/foam.foam')
foamfoam.MeshRegions = ['internalMesh']
foamfoam.CellArrays = ['U', 'alpha.water', 'p', 'p_rgh']

# get animation scene
animationScene1 = GetAnimationScene()

# update animation scene based on data timesteps
animationScene1.UpdateAnimationUsingDataTimeSteps()

# get active view
renderView1 = GetActiveViewOrCreate('RenderView')
# uncomment following to set a specific view size
# renderView1.ViewSize = [1451, 788]

# show data in view
foamfoamDisplay = Show(foamfoam, renderView1)
# trace defaults for the display properties.
foamfoamDisplay.AmbientColor = [0.0, 0.0, 0.0]
foamfoamDisplay.ColorArrayName = [None, '']
foamfoamDisplay.OSPRayScaleArray = 'U'
foamfoamDisplay.OSPRayScaleFunction = 'PiecewiseFunction'
foamfoamDisplay.GlyphType = 'Arrow'
foamfoamDisplay.ScalarOpacityUnitDistance = 0.011743814241555038

# reset view to fit data
renderView1.ResetCamera()

animationScene1.GoToNext()

# reset view to fit data
renderView1.ResetCamera()

# reset view to fit data
renderView1.ResetCamera()

# Properties modified on foamfoamDisplay
foamfoamDisplay.Opacity = 0.1

# create a new 'Contour'
contour1 = Contour(Input=foamfoam)
contour1.ContourBy = ['POINTS', 'p']
contour1.Isosurfaces = [14.672607421875]
contour1.PointMergeMethod = 'Uniform Binning'

# Properties modified on contour1
contour1.ContourBy = ['POINTS', 'alpha.water']
contour1.Isosurfaces = [0.1]

# get color transfer function/color map for 'p'
pLUT = GetColorTransferFunction('p')

# show data in view
contour1Display = Show(contour1, renderView1)
# trace defaults for the display properties.
contour1Display.AmbientColor = [0.0, 0.0, 0.0]
contour1Display.ColorArrayName = ['CELLS', 'p']
contour1Display.LookupTable = pLUT
contour1Display.OSPRayScaleArray = 'p'
contour1Display.OSPRayScaleFunction = 'PiecewiseFunction'
contour1Display.GlyphType = 'Arrow'

# show color bar/color legend
contour1Display.SetScalarBarVisibility(renderView1, True)

# get opacity transfer function/opacity map for 'p'
pPWF = GetOpacityTransferFunction('p')

# hide color bar/color legend
contour1Display.SetScalarBarVisibility(renderView1, False)

# set scalar coloring
ColorBy(contour1Display, ('CELLS', 'alpha.water'))

# rescale color and/or opacity maps used to include current data range
contour1Display.RescaleTransferFunctionToDataRange(True)

# show color bar/color legend
contour1Display.SetScalarBarVisibility(renderView1, True)

# get color transfer function/color map for 'alphawater'
alphawaterLUT = GetColorTransferFunction('alphawater')

# get opacity transfer function/opacity map for 'alphawater'
alphawaterPWF = GetOpacityTransferFunction('alphawater')

# hide color bar/color legend
contour1Display.SetScalarBarVisibility(renderView1, False)

# current camera placement for renderView1
renderView1.CameraPosition = [0.3355744674485359, 0.7879342532852335, 0.11658777124259538]
renderView1.CameraFocalPoint = [0.02500000223517418, 0.0, 0.15000000596046448]
renderView1.CameraViewUp = [0.024322494167508465, 0.032782482044070485, 0.9991665152258165]
renderView1.CameraParallelScale = 0.21937311466552661

# current camera placement for renderView1
renderView1.CameraPosition = [0.3355744674485359, 0.7879342532852335, 0.11658777124259538]
renderView1.CameraFocalPoint = [0.02500000223517418, 0.0, 0.15000000596046448]
renderView1.CameraViewUp = [0.024322494167508465, 0.032782482044070485, 0.9991665152258165]
renderView1.CameraParallelScale = 0.21937311466552661

# save animation images/movie
WriteAnimation('/home/sigveka/Desktop/Tank/water.ogv', Magnification=1, FrameRate=15.0, Compression=True)

# Properties modified on contour1Display
contour1Display.OSPRayScaleArray = 'Normals'

#### saving camera placements for all active views

# current camera placement for renderView1
renderView1.CameraPosition = [0.3355744674485359, 0.7879342532852335, 0.11658777124259538]
renderView1.CameraFocalPoint = [0.02500000223517418, 0.0, 0.15000000596046448]
renderView1.CameraViewUp = [0.024322494167508465, 0.032782482044070485, 0.9991665152258165]
renderView1.CameraParallelScale = 0.21937311466552661

#### uncomment the following to render all views
# RenderAllViews()
# alternatively, if you want to write images, you can use SaveScreenshot(...).