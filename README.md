# premiere_markers_to_youtube

This script takes in a markers file exported from Premiere Pro and outputs a text file that can be used to create YouTube chapters.

### Creating a Markers File

- Add markers to your timeline in Premiere Pro. Be sure you add them to the timeline and not to individual clips (deselect all before adding markers).
- Be sure to add a marker at 0:00 and name it. YouTube requires a beginning chapter at zero.
- Export markers by using File / Export / Markers. This will output a text file but the formatting is not correct for YouTube Chapters.

- Run script:

`python3 premiere_markers_to_youtube.py <path-to-file>`

- The script will reformat the file into YouTube's preferred chapter format and save a text file back into the same directory
- Open the file, copy the text, and paste it in your YouTube description.

 
 
