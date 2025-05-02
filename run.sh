#!/bin/bash

rtl_433 -f 433920000 -R 0 -X 'n=biltema,m=OOK_PWM,s=480,l=1500,r=1450,t=450,g=0,y=0' -F json | python3 foxping.py -L FINE
