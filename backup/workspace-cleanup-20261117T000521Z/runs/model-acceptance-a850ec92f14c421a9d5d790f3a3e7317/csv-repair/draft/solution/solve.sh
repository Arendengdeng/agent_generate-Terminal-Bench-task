#!/bin/sh
# Reference repair: replace the faulty cleaner with a spec-conforming one.
set -eu
cp /solution/clean.py /app/clean.py
chmod 644 /app/clean.py
