## Travis CI Integration


This project is configured to be automatically tested using the Travis continuous integration system, https://travis-ci.org. This includes testing of any pull requests sent to this repo. 

The travis [getting started](https://docs.travis-ci.com/user/getting-started) page nicely documents the procedure to set this up, but to summarize that:
* Sign into the travis-ci website and grant Travis just enough access to your repo to allow Travis to be called when the repo changes (for public repos, this is a very limited permissions bit).
* On your travis profile page, enable travis CI for the repo you want to test.
* Drop a .travis.yaml file at the root of the repository that tells travis how to test the project.
* Push the change. You'll see new UI things inline with the standard github views of project activity. Click them for details.

