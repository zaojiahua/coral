#!/usr/bin/env python3
import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
print(sys.path)
import tracer

if __name__ == '__main__':
    tracer.run()


