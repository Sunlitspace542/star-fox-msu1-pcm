# PCM remapper usage
  
To use, place your Zeldix PCM set in the `input` directory. Assuming the original PCM prefix is already `sfx_msu1`, you shouldn't need to touch anything else (if it is different, edit `remap.bat` and change the prefix to what your set uses). Remapped PCMs will be in the `output` directory.
  
Run `remap.bat`. The resulting output may be missing tracks 42, 43, and 44 (Secret Activated, Black Hole Warp In, Black Hole Warp Out) depending on the set you're using. These can be sourced from my set. Same applies for any other missing tracks (if any). The script will tell you what destination track numbers it couldn't find.  