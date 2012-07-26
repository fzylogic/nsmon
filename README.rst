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

Architecture:
=============

nsmon is fully threaded in order to monitor multiple backend servers in real-time.
Every server to be monitored has its own thread and sends status back to the main
thread via a simple Queue for every event (meaning that if you have a server 
monitoring 4 domains and it goes down, you'll know as soon as the first one fails).

Installation:
=============

Simply copy the nsconfig.yml.example file out of the conf directory
into either into /etc/nsmon or into the same directory as the 
nsmon.py script (useful for testing)
