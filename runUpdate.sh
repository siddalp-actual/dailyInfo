#! /bin/bash
case `/bin/hostname` in
	"Apollo14")
	echo 'running on laptop'
    cd ~/Dropbox/pgm/gkeep
    . ~/.pyenv/versions/gnrlPy/bin/activate
	;;

	"Pi3")
    cd ~/pgm/gkeep
	echo 'running on pi'
    . ~/.pyenv/versions/py3/bin/activate
	;;

	*)
	echo `/bin/hostname`
	;;
esac
./update_note.py
