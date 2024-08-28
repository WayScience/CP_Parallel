# CellProfiler (CP) Parallel

> ⚙️ Speed up your CellProfiler analyses through the power of parallelization!

CP Parallel is a utility function that will help with speeding up image analysis pipelines using [CellProfiler](https://cellprofiler.org/).
Typically, pipelines in CellProfiler include but not limited to:

1. Maximum projections of multiple z-slices per FOV
2. Illumination correction
3. Segmentation and feature extraction

CellProfiler can be run either with the GUI or through headless mode via the terminal.
We prefer to use the headless mode option since it is most reproducible.
One of the major downfalls of headless mode is that you can not run in parallel.

CP Parallel comes in to solve this issue by using a dictionary to call multiple instances of CellProfiler, run in parallel, and output a log file per process.
The current functionality is to run multiple plates in parallel.
Future implementation will include running multiple wells in the same plate in parallel.
