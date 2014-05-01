import os.path
import sys
import math
import pickle
from sortedcontainers import SortedDict
from utils import is_ignored, puzzle
import pHash


class ImageHash(object):
    path = None
    phash = None
    puzzle_vec = None

    def __init__(self, path=None, puzzle_vec=None, phash=None):
        self.path = path
        self.puzzle_vec = puzzle_vec
        self.phash = phash

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return self.path

    def get_puzzle_similarity(self, other):
        vec1 = self.puzzle_vec_uncompressed
        vec2 = other.puzzle_vec_uncompressed
        return int(puzzle.get_distance_from_cvec(vec1, vec2) * 64)

    def get_phash_similarity(self, other):
        return pHash.hamming_distance(self.phash, other.phash)

    @staticmethod
    def get_distance(hash1, hash2):
        return min(
            hash1.get_phash_similarity(hash2),
            hash1.get_puzzle_similarity(hash2)
        )


class Fingerprints(object):
    data = SortedDict()

    def __getstate__(self):
        return (self.output_dir, self.ignore, self.threshold, self.data)

    def __setstate__(self, state):
        try:
            (self.output_dir, self.ignore, self.threshold, self.data) = state
        except Exception as e:
            print "unpickle warning:", e
            self.data = state

    def __init__(self, output_dir, threshold=0.9, ignore=[], ignore_cache=False):
        self.output_dir = output_dir
        self.ignore = ignore
        self.threshold = threshold

        if not ignore_cache and os.path.exists(self._cache_file):
            sys.stdout.write("Existing fingerprints data found. Loading... ")
            sys.stdout.flush()
            with open(self._cache_file, "r") as fp:
                fingerprints = pickle.load(fp)
                print "done."

                self.data = fingerprints.data

    @property
    def output_dir(self):
        return self._output_dir

    @output_dir.setter
    def output_dir(self, value):
        self._output_dir = value
        self._backup_dir = os.path.join(value, ".backup")
        self._cache_file = os.path.join(value, ".fingerprints.pickle")

        if not os.path.exists(self._backup_dir):
            os.makedirs(self._backup_dir)

    @property
    def ignore(self):
        return self._ignore

    @ignore.setter
    def ignore(self, value):
        self._ignore = value

    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, value):
        self._threshold = value
        self.max_distance = int(math.ceil((1 - value) * 64))

    def uncompress(self):
        for obj in self.data.values():
            obj.puzzle_vec_uncompressed = puzzle.uncompress_cvec(obj.puzzle_vec)

    def save(self):
        with open(self._cache_file, "wb") as fp:
            pickle.dump(self, fp)

    def add(self, image_hash):
        if image_hash and image_hash.path not in self.data:
            self.data[image_hash.path] = image_hash

    def is_ignored(self, path):
        return is_ignored(path, self.ignore) and not path.startswith(self._backup_dir)

    def get_duplicates(self, image_hash):
        if not image_hash:
            return None

        # don't consider ourself a duplicate
        results = []
        for path in self.data.keys():
            if path == image_hash.path or self.is_ignored(path):
                continue
            distance = ImageHash.get_distance(image_hash, self.data[path])
            if distance <= self.max_distance:
                results.append((distance, path))
        return results

    def find_hash(self, path):
        return self.data.get(path)
