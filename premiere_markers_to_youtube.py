import csv
import os
import sys

"""
This script takes in a markers file exported from Premiere Pro
and outputs a text file that can be used to create YouTube markers.
Simply copy the text from the output file and paste it into the
YouTube description
"""

# TODO: Copy to clipboard at the end
# TODO: Add a check to see if the file exists
# TODO: Add a check to make sure there is a chapter at 0:00

with open(
    sys.argv[1],
    "r",
    encoding="utf-16",
) as tsvfile:
    reader = csv.reader(tsvfile, delimiter="\t")
    data = list(reader)

filename = sys.argv[1]
filename = filename.split("/")[-1]
file_directory = sys.argv[1].split(filename)[0]

# remove first line from list
data.pop(0)

# removes tabs from data by index
for line in data:
    del line[0:3]

for line in data:
    del line[1:3]

for line in data:
    del line[2:]

# clean up timecode
for line in data:
    line[0] = line[0][3:]

for line in data:
    line[0] = line[0][:-3]

with open("temp_file.txt", "w") as new_file:
    write = csv.writer(new_file, delimiter=" ")
    write.writerows(data)

# re-open and replace quotes
with open("temp_file.txt", "r") as adjust_file:
    filedata = adjust_file.read()

filedata = filedata.replace('"', "")

# write out final file
with open("new_file.txt", "w") as final_file:
    final_file.write(filedata)

# rename file
os.rename("new_file.txt", filename + "_markers.txt")

# move file to directory
os.rename(filename + "_markers.txt", file_directory + filename + "_markers.txt")

# remove temporary file
os.remove("temp_file.txt")

# delete the original file after creating "_markers" file
os.remove(sys.argv[1])
