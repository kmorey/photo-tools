import click
import os
import os.path
import json
import utils
import multiprocessing
import shutil
import pHash
from fingerprints import Fingerprints, ImageHash
from PIL import Image

os.stat_float_times(True)


@click.group()
def cli():
    pass


def calculate(backup_dir, filename):
    cvec = utils.puzzle.get_cvec_from_file(filename)
    if not cvec:
        return None

    return ImageHash(
        puzzle_vec=utils.puzzle.compress_cvec(cvec),
        phash=pHash.imagehash(filename),
        path=filename
    )


def get_duplicates(image_hash):
    """
    utilizes a hack of storing the fingerprints (can be large) into globals()
    for each process to keep things optimal for multiprocessing
    """
    fingerprints = globals()['fingerprints']
    return (image_hash, fingerprints.get_duplicates(image_hash))


def get_best_match(images):
    if len(images) == 1:
        return images[0]

    best_match = None
    best_size = (0, 0)
    for distance, image_path in images:
        img = Image.open(image_path)
        size = img.size
        if max(*size) > max(*best_size) and min(*size) > min(*best_size):
            best_match = (distance, image_path)
            best_size = img.size

    return best_match


def get_file_date(filepath):
    """
    get the creation time or modification time, whichever is older
    """
    stat = os.stat(filepath)
    return min(stat.st_mtime, stat.st_ctime)


def get_new_image_path(filepath, num, dest, format_str="IMG_{0:05d}{1}"):
    root, ext = os.path.splitext(filepath)
    return os.path.join(dest, format_str.format(num, ext.lower()))


@cli.command()
@click.argument('files', nargs=-1, help="a list of files to compare")
@click.option('--threshold', '-t', default=0.9, help="similarity threshold", type=click.FLOAT)
def compare(files, threshold):
    import tempfile
    import glob

    tempdir = tempfile.mkdtemp()
    print tempdir

    for filepath in files:
        shutil.copy2(filepath, tempdir)

    files = glob.glob(os.path.join(tempdir, '*'))
    fingerprints = Fingerprints(output_dir=tempdir, threshold=threshold)
    globals()['fingerprints'] = fingerprints

    results = utils.apply_async(calculate, [
        (tempdir, filepath) for filepath in files
    ])
    for r in results:
        fingerprints.add(r)
    fingerprints.uncompress()

    for filepath in files:
        duplicates = get_duplicates(fingerprints.find_hash(filepath))
        print duplicates


@cli.command()
@click.argument('dest')
@click.argument('sources', help="comma-separated list of source directories", nargs=-1)
@click.option('--threshold', '-t', default=0.9, help="similarity threshold", type=click.FLOAT)
@click.option('--ignore', '-i', multiple=True)
@click.option('--clean', is_flag=True, default=False, help="clear caches before running")
@click.option('--normalize/--no-normalize', default=True)
@click.option('--cpus', default=multiprocessing.cpu_count())
def process(sources, dest, threshold, ignore, clean, normalize, cpus):
    sources = utils.normalize_paths(list(sources))
    ignore = utils.normalize_paths(list(ignore) + [dest])

    fingerprints = Fingerprints(output_dir=dest, threshold=threshold, ignore=ignore)
    duplicates_file = os.path.join(dest, ".duplicates.json")

    print "Max distance of similarity:", fingerprints.max_distance

    # to get progress, count the total number of files we will touch
    files = []
    for source in sources:
        files += utils.walker(source, lambda x: x, ignore=ignore)

    print "Processing {0} files.".format(len(files))

    if len(files) == 0:
        print "No files found."
        quit()

    if normalize:
        print "Normalizing images..."
        files = utils.apply_async(utils.normalize_image, [
            (fingerprints._backup_dir, filepath, clean) for filepath in files
        ], cpus=cpus)

    need_fingerprint = [
        (fingerprints._backup_dir, filepath)
        for filepath in files if not fingerprints.find_hash(filepath)
    ]

    if need_fingerprint:
        def save_progress(results):
            for r in results:
                fingerprints.add(r)
            fingerprints.save()
            print "Saved."

        print "Calculating fingerprints for {0} files...".format(len(need_fingerprint))
        results = utils.apply_async(calculate, need_fingerprint,
                                    aborted_callback=save_progress, cpus=cpus)
        save_progress(results)

    fingerprints.uncompress()

    output = {"threshold": threshold, "duplicates": {}}
    if os.path.exists(duplicates_file):
        with open(duplicates_file, 'r') as fp:
            loaded = json.load(fp)
            if loaded.get("threshold") == threshold:
                output = loaded

    output_duplicates = output.get("duplicates", {})

    # we need to recalculate *all* duplicate information if there is a new file
    # added since the last time we ran, since it might be a duplicate of anything
    # TODO: handle ctrl-c again
    old_duplicates = set(output_duplicates.keys())
    missing_duplicate_info = set(files) - old_duplicates

    if missing_duplicate_info:
        need_duplicate = files
        output_duplicates.clear()
    else:
        need_duplicate = [
            filepath for filepath in files if filepath not in output_duplicates.keys()
        ]

    # seen_files = []
    # for filepath, duplicate_files in output_duplicates.iteritems():
    #     seen_files.append(filepath)
    #     for distance, duplicate_path in duplicate_files:
    #         seen_files.append(duplicate_path)

    if need_duplicate:
        print "Looking for duplicates for {0} files...".format(len(need_duplicate))

        def save_progress(results):
            for image_hash, duplicates in results:
                if not image_hash:
                    continue

                filepath = image_hash.path
                output_duplicates[filepath] = duplicates

            with open(duplicates_file, "w") as fp:
                json.dump(output, fp)

            print "Saved."

        def setup(fingerprints):
            """
            hack: store the fingerprints into globals for each process so the worker
            function can pull them from globals()
            """
            globals()['fingerprints'] = fingerprints

        results = utils.apply_async(
            get_duplicates,
            [(fingerprints.find_hash(filepath),) for filepath in need_duplicate],
            pool_args=dict(
                initializer=setup,
                initargs=(fingerprints,)
            ),
            aborted_callback=save_progress,
            cpus=cpus
        )

        # results = []
        # setup(fingerprints)
        # progress = utils.Progress(len(need_duplicate))
        # for filepath in need_duplicate:
        #     results.append(get_duplicates(fingerprints.find_hash(filepath)))
        #     progress.incr()
        # progress.done()

        save_progress(results)

    keys = sorted(output_duplicates.keys(), key=get_file_date)

    seen_files = []
    count = 0
    duplicates_count = 0
    duplicates_dest = os.path.join(dest, "duplicates")
    for filepath in keys:
        if filepath in seen_files:
            continue

        duplicates = output_duplicates[filepath]
        count += 1
        seen_files.append(filepath)
        seen_files.extend([duplicate_path for distance, duplicate_path in duplicates])

        all_files = [(0, filepath)] + duplicates
        distance, best_image = get_best_match(all_files)
        new_filepath = get_new_image_path(best_image, count, dest)
        print "Copying {0} to {1}".format(best_image, new_filepath)
        shutil.copy2(best_image, new_filepath)

        if duplicates:
            duplicates_count += 1
            filedest = os.path.join(duplicates_dest, str(duplicates_count))

            all_files = [(distance, filepath)] + duplicates
            for idx, (distance, filepath) in enumerate(all_files, start=1):
                # only copy non-exact matches for spot checking
                if distance > 0 and filepath != best_image:
                    if not os.path.isdir(filedest):
                        os.makedirs(filedest)
                    shutil.copy2(
                        filepath,
                        get_new_image_path(
                            filepath,
                            idx,
                            filedest,
                            "{0}_{1}".format(distance, "{0}{1}")
                        )
                    )

            if os.path.isdir(filedest):
                shutil.copy2(
                    new_filepath, get_new_image_path(new_filepath, None, filedest, "kept{1}")
                )

if __name__ == "__main__":
    cli()
