~~~~~
nsmon
~~~~~

A tiny, opensource monitoring daemon for anycasted or load-balanced DNS systems


Dependencies:
=============

* Python (tested with 2.7)
* DNS python module
* yaml python module


Optional dependencies:
======================

* Graphite
* Quagga or a load balancer with a usable/scriptable CLI


Installation:
=============

Simply copy the nsconfig.yml.example file out of the conf directory
into either into /etc/nsmon or into the same directory as the 
nsmon.py script (useful for testing)
