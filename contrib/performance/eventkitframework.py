import objc as _objc

__bundle__ = _objc.initFrameworkWrapper("EventKit",
    frameworkIdentifier="com.apple.EventKit",
    frameworkPath=_objc.pathForFramework(
    "/System/Library/Frameworks/EventKit.framework"),
    globals=globals())
