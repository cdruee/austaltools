:orphan:

-------------------
austaltools heating
-------------------

heating description file ``heating.yaml``
-----------------------------------------

**The basic structure:**

The top tag is ``buildings``. Below this, there is a named list
of one or multiple buildings. The keys are the user-given building names;
the names must be unique and not contain spaces.

Each builting must contain an associative array containing the tags
``hvac``, ``room``, and ``walls``. ::

    buildings:
      mybuilding:
        hvac:
          ...
        rooms:
          ...
        walls:
          ...

      2ndbuilding:
        t_out: 0.
        t_soil: 9.
        hvac:
          ...
        rooms:
          ...
        walls:
          ...

Optionally, for each building
  - ``t_out`` (number) the initial air temperature in °C,
  - ``t_soil`` (number) the initial soil temperature in °C

may be given. If not given, the starting values are intialized
as :class:`numpy.nan`

**hvac (Heating, Ventilation and Airconditioning Control):**

Contains an associative array containing the tags
``modes``, and ``timers``. Both must contain at least one entry.

``modes`` is a named list of one or multiple heating settings.
    The keys are the user-given names of the modes;
    the names must be unique and not contain spaces.
    Each entry in ``modes`` contains an associative
    array containing the tags:

      - ``roomtemp`` (optional) ist the room target temperature in °C.
        If missing, the room temperature is not limited
        (i.e. the heating always operates at constant power)
      - ``throttle`` (optional) is the available fraction in %
        of the maximum heating power installed in a room.
        If missing, 100% is assumed
        (i.e. the heating uses the full installed power)

    Both tags may contain either one number
    **or** an associtative list. In the latter case, the keys of this list
    are the names of the rooms defined in the section ``rooms``.
    One, multiple or all names may be missing, if the list contains the
    key (i.e. pseudo room name) ``_default``.
    This value is applied to all rooms not listed explicitly.



``timers`` is a named list of one or multiple timer configuration.
    The keys are the user-given names of the timers;
    the names must be unique and not contain spaces.
    Each entry in ``timers`` contains an associative
    array containing the tags:

      - ``start`` (optional, string) is the first date,
        on which the timer is applied. The format ist ``mm-dd``,
        where ``mm`` is the thwo-digit month and
        ``dd`` the two-digit day of month.

        ``start`` is **required**, if more than one timer is defined.

      - ``switch`` (required) is the list of switching times.
        Each list entry must contain the tags:

          - ``mode`` (required, string) is the name of the mode -
            defined under ``modes`` - that is activated at this time.
          - ``hhmm`` (required, string) the time at which the mode
            is to be activated. The format ist ``hhmm``,
            where ``hh`` is the thwo-digit hour and
            ``mm`` the two-digit minute.
          - ``week`` (optional, string) a string representig the weekdays
            that indicates, on which days of week the item is applied.
            ``mtwtfss`` indicates it is applied on all week days.
            Each day replaced by a minus (``-``) the item is deactivated.
            For example ``mtwtf--`` signalys "only Monday to Friday" or
            ``-----ss`` is "Weekend only".


example: ::

    buildings:
      mybuilding:
        hvac:
          modes:
            high:
              roomtemp:
                bathroom: 24
                _default: 20
              throttle: 100
            low:
              roomtemp: 15
              throttle: 25
          timers:
            winter:
              start: 10-01
              switch:
                - mode: high
                  hhmm: 0900
                - mode: low
                  hhmm: 1800
            summer:
              start: 05-01
              switch:
                - mode: low
                  hhmm: 0000

        ...


**walls (also including floors and ceiling):**

``walls`` is a named list of the wall elements.
    The keys are the user-given names of the wall elements;
    the names must be unique and not contain spaces.

    Each entry is an associtative list containing the following tags:
      - ``d`` (required, number) thickness of the wall in m.
        The minimum value is :py:const:`austaltools.heating.WALL_SLAB`
      - ``room_w`` (required, string) name of the room on the warm side
        of the wall. I.e. a positive sign of the heat flux density
        corresponds to a heat loss in this room.
      - ``room_c`` (required, string) name of the room on the cold side
        of the wall.
      - ``width`` (optional, number) length of the wall in m,
        meant to represent the horizontal extent in case of
        vertical or slanted walls.
        If missing, ``area`` is required.
      - ``length`` (optional, number) height of the wall in m,
        meant to represent the length along the wall
        (not vertical projection) in case of slanted walls.
        If missing, ``area`` is required.
      - ``area`` (optional, number) area of the wall in :math:`m^2`,
        including contained other wall elements (e.g. windows),
        overrides the product of ``width`` and ``length``.
        If missing, ``width`` and ``length`` are required.
      - c (optional, number) heat capacity of the wall in
        :math:`J kg^{-1}K^{-1}`,
        defaults to :math:`836 J kg^{-1}K^{-1}` (massive brick wall).
      - k (optional, number) heat conductivity of the wall in
        :math:`W m^{-1}K^{-1}`,
        defaults to :math:`0.58 Wm^{-1}K^{-1}` (massive brick wall).
      - rho (optional, number) density of the wall in
        :math:`kg m^{-3}`,
        defaults to :math:`1400 kg m^{-3}` (massive brick wall).
      - partof (optional, string) name of another wall emelent that
        fully contains this wall element (e.g. in case of a window).
        The area of the containing wall element is reduced by the
        area of thins wall ement.

        The containing wall ement must be defined before this
        wall element. The area of the containing wall ement must be
        larger than the area of this wall element.
      - t_start (optional, number) initial temperature of the
        whole wall. If missing, a linear profile between the
        temperatures in rooms ``room_w`` and  ``room_c`` is assumed.


Example::

    buildings:
      mybuilding:
        hvac:
          ...
        rooms:
          myroom:
            ...
        walls:
          front_wall:
            d: 0.3
            h: 2.5
            l: 5.0
            room_c: outside
            room_w: myroom
          front_door:
            partof: front_wall
            d: 0.04
            area: 2.
            room_c: outside
            room_w: myroom
          ceiling:
            c: 1500
            d: 0.1
            h: 5.0
            k: 0.15
            l: 5.0
            rho: 600.0
            room_c: soil
            room_w: myroom

**rooms (and special pseudo rooms):**

``room`` is a named list of the room.
    The keys are the user-given names of the rooms;
    the names must be unique and not contain spaces.

    Each entry is an associtative list containing the follwing tags:
      - ``width`` (optional, number) width of the room in m.
        If missing, ``area`` is required.
      - ``length`` (optional, number) lenght of the room in m,
        orthogonal to ``width`` in case of non-square rooms.
        If missing, ``area`` is required.
      - ``height`` (optional, number) height of the room in m,
        If missing, ``volume`` is required.
      - ``area`` (optional, number) area of the wall in :math:`m^2`,
        overrides the product of ``width`` and ``length``.
        If missing, ``width`` and ``length`` are required.
      - ``volume`` (optional, number) volume of the room in :math:`m^3`,
        overrides the product of either ``width`` and ``length``
        or ``area``, and ``height``.
        If missing, either ``width`` and ``length``
        or ``area``, and ``height`` are required.
      - ``maxpower`` (optional, number) the maximum power of the heating
        installed in the room in :math:`W`.
        **Required** for all rooms except special rooms.
        If missing :math:`0. W`, i.e. unheated room, is assumed.
      - ``p_set`` (optional, number) the power throttling in %
        of the heater in the room. If missing :class:`numpy.nan` is assumed,
        i.e. no temperature regulation.
      - ``t_set`` (optional, number) the target temperature In °C
        for the room. If missing 100 % is assumed,
        i.e. the heater can use its full power.
      - ``special`` (optional, boolean) is True if the room is
        not a real room, but a time-invariant heat reservoir.
        In every building the special rooms `outside` and `soil`
        are created automatically.

Example::

    buildings:
      mybuilding:
        hvac:
          ...
        rooms:
          room:
            width: 5.0
            height: 2.5
            lenght: 5.0
            maxpower: 13000.
            t_set: 20.
            t_start: 20.
        walls:
          ...

