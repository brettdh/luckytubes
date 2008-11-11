# Just for convenient creation of distribution tarballs.
# You do not need to run this makefile!
DATE=`date +"%m-%d-%Y"`
all:
	echo "No compiling needed!"
	echo "Makefile is for generating tarballs with make dist."

dist: luckytubes.py youtubedl.py
	git archive --format=tar --prefix=luckytubes-${DATE}/ HEAD | gzip > luckytubes-${DATE}.tar.gz
	git archive --format=tar --prefix=luckytubes-${DATE}/ HEAD | bzip2 > luckytubes-${DATE}.tar.bz2
	git archive --format=zip --prefix=luckytubes-${DATE}/ HEAD > luckytubes-${DATE}.zip