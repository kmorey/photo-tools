import multiprocessing
import sys
import datetime
import time
import os
import os.path
import pexif
import shutil
import hashlib
from PIL import Image
from pypuzzle import Puzzle

PHOTO_TYPES = ['.jpg', '.png', '.gif', '.jpeg']
puzzle = Puzzle()

puzzle.set_max_width(9000)
puzzle.set_max_height(9000)
# puzzle.set_autocrop(0)
# puzzle.set_contrast_barrier_for_cropping(5)
# puzzle.set_noise_cutoff(1)
# puzzle.set_p_ratio(1.0)
# puzzle.set_lambdas(18)


class Progress(object):
    last_msg = ""

    def __init__(self, total):
        self.count = 0
        self.total = total
        self.start = datetime.datetime.now()

    def incr(self):
        self.update(self.count + 1)

    def update(self, value):
        self.count = value or 1
        seconds_elapsed = datetime.datetime.now() - self.start
        avg_time = float(seconds_elapsed.total_seconds()) / self.count
        seconds_estimate = (self.total - self.count) * avg_time

        hours, remainder = divmod(int(seconds_estimate), 3600)
        minutes, seconds = divmod(remainder, 60)

        self.last_msg = "{erase}{percent:0.2f}% ({time})".format(
            erase="\b" * len(self.last_msg),
            percent=self.count * 100.0 / self.total,
            time="{h:02d}:{m:02d}:{s:02d}".format(h=hours, m=minutes, s=seconds)
        )
        sys.stdout.write(self.last_msg)
        sys.stdout.flush()

    def done(self):
        print ""


def is_ignored(path, ignore=[]):
    """
    check whether a path should be ignored
    """
    for ignored in ignore:
        if path.startswith(ignored):
            return True
    return False


def apply_async(fn, items, pool_args={}, aborted_callback=None, cpus=multiprocessing.cpu_count()):
    """
    wrapper around multiprocessing.Pool.apply_async but also prints progress
    along the way
    """
    try:
        pool = multiprocessing.Pool(processes=cpus, **pool_args)
        progress = Progress(len(items))
        results = [pool.apply_async(fn, item) for item in items]

        finished = []
        while True:
            done = 0
            todo = 0
            for r in results:
                if r.ready():
                    if not r.successful():
                        raise Exception(r.get())
                        quit()
                    if r not in finished:
                        finished.append(r)
                    done += 1
                else:
                    todo += 1
            progress.update(done)

            if done == len(results):
                break
            time.sleep(1)
        progress.done()
        pool.close()
        return [r.get() for r in results]
    except KeyboardInterrupt:
        if aborted_callback:
            print "\nAbort signal caught. Saving progress..."
            aborted_callback([r.get() for r in finished])
        sys.exit(1)


def walker(path, callback, ignore=[]):
    """
    recursively walk a path looking for image files and calling callback on
    each file.

    ignore any file within the paths provided to ignore
    """
    results = []
    for (dirpath, dirnames, filenames) in os.walk(path):
        if is_ignored(dirpath, ignore):
            continue
        for name in filenames:
            basename, ext = os.path.splitext(name)
            if ext.lower() in PHOTO_TYPES:
                path = os.path.join(dirpath, name)
                results.append(callback(path))
    return results


def normalize_paths(paths):
    """
    remove trailing path separator if included
    """
    for idx, path in enumerate(paths):
        if paths[idx][-1:] == os.sep:
            paths[idx] = paths[idx][:-1]
    return paths


def normalize_image(backup_dir, filepath, ignore_cache):
    """
    normalize images to exif orientation 1 if necessary

    copy the file to the backup_dir before modifying in case something goes wrong

    if the orientation is already good, touch a file in the backup dir so we don't
    have to scan exif next time
    """
    name, ext = os.path.splitext(filepath)
    if ext.lower() == '.jpg':
        md5 = hashlib.md5(filepath).hexdigest()
        new_filepath = os.path.join(backup_dir, '{0}.jpg'.format(md5))
        if not ignore_cache and os.path.exists(new_filepath):
            return new_filepath if os.path.getsize(new_filepath) else filepath

        try:
            exif_img = pexif.JpegFile.fromFile(filepath)
            if hasattr(exif_img.exif.primary, 'Orientation'):
                orientation = exif_img.exif.primary.Orientation[0]
                if orientation in [2, 3, 4, 5, 6, 7, 8]:
                    shutil.copy2(filepath, new_filepath)
                    old_filepath, filepath = filepath, new_filepath

                    exif_img.exif.primary.Orientation = [1]
                    exif_img.writeFile(new_filepath)

                    img = Image.open(new_filepath)
                    if orientation is 6:
                        img = img.rotate(-90)
                    elif orientation is 8:
                        img = img.rotate(90)
                    elif orientation is 3:
                        img = img.rotate(180)
                    elif orientation is 2:
                        img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation is 5:
                        img = img.rotate(-90).transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation is 7:
                        img = img.rotate(90).transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation is 4:
                        img = img.rotate(180).transpose(Image.FLIP_LEFT_RIGHT)

                    img.save(new_filepath)
                    shutil.copystat(old_filepath, new_filepath)
                else:
                    # touch the file to create a 0 byte "cache"
                    open(new_filepath, 'a').close()
        except Exception:
            # can't read exif to try to fix orientation, move along
            pass
    return filepath
