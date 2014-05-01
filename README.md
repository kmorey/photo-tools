photo-tools
===========

A tool to find duplicate and similar images across many source folders and
provide a way to clean up the extra files.

The original photos are not touched during the process to avoid data loss.
Rotation can be performed on photos that have EXIF orientation data so they
can match a possible duplicate that may not.

The entire process can be quite lengthy and supports aborting (`ctrl-c`) and
resuming as close to where it left off as possible. Cache files are created
for the rotate step and the fingerprints are kept around once calculated. These
caches can be ignored on subsequent runs with the `--clean` flag.

Process
-------

1. Search the source folders for exact duplicates, pick one to keep and skip the others (not implemented)
2. Rotate images to account for EXIF orientation
3. Calculate a fingerprint for every image (libpuzzle)
4. Compare fingerprints to find similar photos within threshold
5. Copy all originals to the destination folder, skipping those flagged as similar. This step will inspect each duplicate and retain the largest resolution file.
6. Clean up caches (can be large) upon successful completion (not implemented)

Example Usage
-------------

To search within ~/Photos and ~/OLD_Photos for images 90% similar to each other
and copy the best ones to "~/Cleaned Photos" you can do something like this:

    python photo-tools.py process -t0.9 ~/Cleaned\ Photos/ ~/Photos ~/OLD_Photos

You can also ignore subfolders if necessary:

    python photo-tools.py process -t0.9 --ignore ~/Photos/Thumbnails ~/Cleaned\ Photos/ ~/Photos


Options
-------
`-t/--threshold` float (0.0-1.0) of how similar photos must be to be flagged

`-i/--ignore` (multi) paths to ignore processing, probably subfolders

`--clean` ignore caches and reprocess everything

`--no-normalize` skip normalizing images (rotating to account for orientation)

TODO
----

* CRC check images for exact duplicates first