# CalendarServer's Master/Worker Architecture

## Overview

When CalendarServer starts it creates a _Master_ process that listens on the configured HTTP ports. The _Master_ process also spawns a set of _Worker_ processes. When the _Master_ process accepts a connection from an HTTP client it hands off the socket to a _Worker_ process. The _Worker_ process then handles the HTTP request(s) and closes the socket.

## Details

The majority of the code for what is described below can be found in the `txweb2.metafd` Python module. Details on the key class in that module are below.

When the _Master_ process starts up it spawns the _Worker_ processes (the number set via the `config.ProcessCount` setting). The _Master_ will monitor each _Worker_ process and if the _Worker_ dies it will re-spawn a new one to ensure there are always a fixed number of _Workers_ running. The _Master_ process also creates its own socket that is used as a feedback channel for _Worker_ processes. The socket can either be a unix socket (set via `config.ControlSocket` - the default) or a TCP socket (set via `config.ControlPort` - set to zero to disable). The _Master_ process also maintains internal tables for each _Worker_ process so it can track activity and status of each _Worker_ (see `txweb2.metafd.WorkerStatus`).

When a _Worker_ process is started, it creates a `txweb2.metafd.ReportingHTTPService` that is a special HTTP service that can communicate back to the _Master_ process to signal state changes in the _Worker_. The _Worker_ reports the following activity:

* ready to start receiving requests: _Worker_ sends a `0` character over the control socket
* socket has been received: _Worker_ sends a `+` character over the control socket
* socket has been closed: _Worker_ sends a `-` character over the control socket

The _Master_ uses those messages to track the number of outstanding socket connections sent to the _Worker_ and still being processed by the _Worker_. The _Master_ uses that information to determine which _Worker_ process receives the next socket when an HTTP client connects. The _Master_ will pick the _Worker_ with the least active connections, and also limit the _Workers_ to at most `config.MaxRequest` number of active connections. If all the _Workers_ are at their maximum capacity, the _Master_ stops accepting new connections until a _Worker_ reports a socket has been closed and thus a slot has become free for a new HTTP connection to be processed.

### txweb2.metafd.ConnectionLimiter

This class is the main service started by the _Master_ to listen on the configured HTTP sockets and to dispatch new client connections to the appropriate _Worker_ process. It uses a `twext.internet.sendfd.InheritedSocketDispatcher` class to manage the sending of the _Master_ accepted socket to the _Worker_ process. It creates one `txweb2.metafd.LimitingInheritingProtocolFactory` per HTTP port to listen on. 

### txweb2.metafd.LimitingInheritingProtocolFactory

This class listens on a specific HTTP port and dispatches incoming connections to a _Worker_ process. It uses the `txweb2.metafd.ConnectionLimiter` to do that. It also manages pausing accepts on the HTTP socket if the _Workers_ are over loaded.

### txweb2.metafd.WorkerStatus

This class maintains the status of each _Worker_ process slot. Note that this status is persistent and tied to a _Worker_ id, not an actual _Worker_ process. So if a _Worker_ process dies and is re-spawned by the _Master_ it will be linked to the `WorkerStatus` object tied to its id (and used by the process that just died). Please read the docstr in `WorkerStatus.__init__` for details about the properties that the class maintains. These are exposed in the `dashboard` tool's _HTTP Slots_ table.

### txweb2.metafd.ReportingHTTPService

This class is the service started by each _Worker_. Starts listening for sockets sent by the _Master_ and reports back the `0` started message over the control socket.

### txweb2.metafd.ReportingHTTPFactory

This class is the factory class for socket connections received by the _Worker_ from the _Master_. It reports back the `+` and `-` messages over the control socket when the socket is received and when it is closed.
