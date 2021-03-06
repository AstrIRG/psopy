"""
minimize.py - SciPy Compatible PSO Solver for Minimization
==========================================================

The implementation of the Particle Swarm Optimization solver. The function
``psopy.minimize_pso`` mimics the interface of ``scipy.optimize.minimize``,
excluding the ``method`` parameter.

``psopy.minimize_pso`` calls the function ``psopy.pswarmopt`` to actually
perform the minimization. Using this function directly allows for a slightly
faster implementation that does away with the need for additional recursive
calls needed to translate the constraints and objective function into the
required structure.

=================== ===========================================================
Functions
===============================================================================
pswarmopt           Optimize under optional constraints using a particle swarm.
minimize_pso        SciPy compatible interface to ``pswarmopt``.
=================== ===========================================================

"""

import functools as ft
import numpy as np
from scipy.spatial import distance
from scipy.optimize import OptimizeResult

from .constraints import gen_confunc

_status_message = {
    'success': 'Optimization terminated successfully.',
    'maxiter': 'Maximum number of iterations has been exceeded.',
    'conviol': 'Unable to satisfy constraints at end of iterations.',
    'pr_loss': 'Desired error not necessarily achieved due to precision loss.'
}


def pswarmopt(fun, x0, confunc=None, friction=.8, max_velocity=5.,
              g_rate=.8, l_rate=.5, max_iter=1000, stable_iter=100,
              ptol=1e-6, ctol=1e-6, callback=None):
    """Internal implementation for ``minimize_pso``.

    See Also
    --------
    psopy.minimize_pso : The SciPy compatible interface to this function. It
        includes the rest of the documentation for this function.
    psopy.gen_confunc : Utility function to convert SciPy style constraints
        to the form required by this function.

    Parameters
    ----------
    x0 : array_like of shape (N, D)
        Initial position to begin PSO from, where ``N`` is the number of points
        and ``D`` the dimensionality of each point. For the constrained case
        these points should satisfy all constraints.
    fun : callable
        The objective function to be minimized. Must be in the form
        ``fun(pos, *args)``. The argument ``pos``, is a 2-D array for initial
        positions, where each row specifies the position of a different
        particle, and ``args`` is a tuple of any additional fixed parameters
        needed to completely specify the function.
    confunc : callable
        The function that describes constraints. Must be of the form
        ``confunc(pos)`` that returns the constraint matrix.

    Notes
    -----
    Using this function directly allows for a slightly faster implementation
    that does away with the need for the additional recursive calls needed to
    wrap the constraint and objective functions for compatibility with Scipy.

    Examples
    --------
    These examples are identical to those laid out in ``psopy.minimize_pso``
    and serve to illustrate the additional overhead in ensuring compatibility.

    >>> import numpy as np
    >>> from psopy import pswarmopt

    Consider the problem of minimizing the Rosenbrock function implemented as
    ``scipy.optimize.rosen``.

    >>> from scipy.optimize import rosen
    >>> fun = lambda x: np.apply_along_axis(rosen, 1, x)

    Initialize 1000 particles and run the minimization function.

    >>> x0 = np.random.uniform(0, 2, (1000, 5))
    >>> res = pswarmopt(fun, x0, stable_iter=50)
    >>> res.x
    array([1.00000003, 1.00000017, 1.00000034, 1.0000006 , 1.00000135])

    Consider the constrained optimization problem with the objective function
    defined as:

    >>> fun = lambda x: (x[0] - 1)**2 + (x[1] - 2.5)**2
    >>> fun_ = lambda x: np.apply_along_axis(fun, 1, x)

    and constraints defined as:

    >>> cons = ({'type': 'ineq', 'fun': lambda x:  x[0] - 2 * x[1] + 2},
    ...         {'type': 'ineq', 'fun': lambda x: -x[0] - 2 * x[1] + 6},
    ...         {'type': 'ineq', 'fun': lambda x: -x[0] + 2 * x[1] + 2},
    ...         {'type': 'ineq', 'fun': lambda x: x[0]},
    ...         {'type': 'ineq', 'fun': lambda x: x[1]})

    Initializing the constraint function and feasible solutions:

    >>> from psopy import init_feasible, gen_confunc
    >>> x0 = init_feasible(cons, low=0., high=2., shape=(1000, 2))
    >>> confunc = gen_confunc(cons)

    Running the constrained version of the function:

    >>> res = pswarmopt(fun_, x0, confunc=confunc, options={
    ...     'g_rate': 1., 'l_rate': 1., 'max_velocity': 4., 'stable_iter': 50})
    >>> res.x
    array([ 1.39985398,  1.69992748])

    """
    # Initialization.
    position = np.copy(x0)
    velocity = np.random.uniform(-max_velocity, max_velocity, position.shape)

    pbest = np.copy(position)
    gbest = pbest[np.argmin(fun(pbest))]

    stable_max = 0
    stable_count = 0
    for ii in range(max_iter):
        # Store for threshold comparison.
        gbest_fit = fun(gbest[None])[0]

        # Determine the velocity gradients.
        dv_g = g_rate * np.random.uniform(0, 1) * (gbest - position)
        if confunc is not None:
            leaders = np.argmin(
                distance.cdist(position, pbest, 'sqeuclidean'), axis=1)
            dv_l = l_rate * \
                np.random.uniform(0, 1) * (pbest[leaders] - position)
        else:
            dv_l = l_rate * np.random.uniform(0, 1) * (pbest - position)

        # Update velocity and clip.
        velocity *= friction
        velocity += (dv_g + dv_l)
        np.clip(velocity, -max_velocity, max_velocity, out=velocity)

        # Update the local and global bests.
        position += velocity
        to_update = (fun(position) < fun(pbest))
        if confunc is not None:
            to_update &= (confunc(position).sum(axis=1) < ctol)

        if to_update.any():
            pbest[to_update] = position[to_update]
            gbest = pbest[np.argmin(fun(pbest))]

        # Termination criteria.
        if np.abs(gbest_fit - fun(gbest[None])[0]) < ptol:
            stable_count += 1
            if stable_count == stable_iter:
                stable_max = stable_count
                break
        else:
            if stable_count > stable_max:
                stable_max = stable_count
            stable_count = 0

        # Final callback.
        if callback is not None:
            position = callback(position)

    if confunc is not None and confunc(gbest[None]).sum() > ctol:
        status = 1
        message = _status_message['conviol']
    elif ii == max_iter:
        status = 2
        message = _status_message['maxiter']
    else:
        status = 0
        message = _status_message['success']

    result = OptimizeResult(x=gbest, fun=fun(gbest[None])[0], status=status,
                            message=message, nit=ii, nsit=stable_max,
                            success=(not status))

    if confunc is not None:
        result.cvec = confunc(gbest[None])

    return result


def minimize_pso(fun, x0, args=(), constraints=(), tol=None, callback=None,
                 options=None):
    """Minimization of scalar function of one or more variables using Particle
    Swarm Optimization (PSO).

    Parameters
    ----------
    fun : callable
        The objective function to be minimized. Must be in the form
        ``fun(x, *args)``. The optimizing argument, ``x``, is a 1-D array of
        points, and ``args`` is a tuple of any additional fixed parameters
        needed to completely specify the function.
    x0 : array_like of shape (N, D)
        Initial position to begin PSO from, where ``N`` is the number of points
        and ``D`` the dimensionality of each point.
    args : tuple, optional
        Extra arguments passed to the objective function.
    constraints : tuple
        Constraints definition. Each constraint is defined in a dictionary with
        fields:

            type : str
                Constraint type. ``scipy.optimize.minimize`` defines ‘eq’ for
                equality and ‘ineq’ for inequality. Additionally, we define
                'stin' for strict inequality and 'ltineq' for less-than
                non-strict inequality.
            fun : callable
                The function defining the constraint.
            args : sequence, optional
                Extra arguments to be passed to the function.

        Equality constraints require the constraint function result to be zero,
        strict inequality require it to be negative and inequality require it
        to be non-positive.
    tol : float, optional
        Tolerance for termination and constraint adjustment. For detailed
        control, use options.
    callback : callable, optional
        Called after each iteration on each solution vector.
    options : dict, optional
        A dictionary of solver options:

            friction : float, optional
                Velocity is scaled by friction before updating, default 0.8.
            g_rate : float, optional
                Global learning rate, default 0.8.
            l_rate : float, optional
                Local (or particle) learning rate, default 0.5.
            max_velocity : float, optional
                Threshold for velocity, default 5.0.
            max_iter : int, optional
                Maximum iterations to wait for convergence, default 1000.
            stable_iter : int, optional
                Number of iterations to wait before Swarm is declared stable,
                default 100.
            ptol : float, optional
                Change in position should be greater than ``ptol`` to update,
                otherwise particle is considered stable, default 1e-6.
            ctol : float, optional
                Acceptable error in constraint satisfaction, default 1e-6.
            sttol : float, optional
                Tolerance to convert strict inequalities to non-strict
                inequalities, default 1e-6.
            eqtol : float, optional
                Tolerance to convert equalities to non-strict inequalities,
                default 1e-7.

    Returns
    -------
    result : scipy.optimize.OptimizeResult
        The optimization result represented as a ``OptimizeResult`` object. The
        following keys are supported,

            x : array_like
                The solution vector.
            success : bool
                Whether or not the algorithm successfully converged.
            status : int
                Termination status. 0 if successful, 1 if max. iterations
                reached, 2 if constraints cannot be satisfied.
            message : str
                Description of the cause of termination.
            nit : int
                Number of iterations performed by the swarm.
            nsit : int
                Maximum number of iterations for which the algorithm remained
                stable.
            fun : float
                Value of objective function for x.
            cvec : float
                The constraint vector for x (only when constraints specified).

    See Also
    --------
    psopy.pswarmopt : Internal implementation for PSO. May be faster to use
        directly.
    psopy.gen_confunc : Converts the constraints definition to a function
        that returns the constraint matrix when run on the position matrix.

    Notes
    -----
    Particle Swarm Optimization (PSO) [1]_ is a biologically inspired
    metaheuristic for finding the global minima of a function. It works by
    iteratively converging a population of randomly initialized solutions,
    called particles, toward a globally optimal solution. Each particle in the
    population keeps track of its current position and the best solution it has
    encountered, called ``pbest``. Each particle has an associated
    velocity used to traverse the search space. The swarm keeps track of the
    overall best solution, called ``gbest``. Each iteration of the swarm
    updates the velocity of the particle toward a weighted sum of the ``pbest``
    and ``gbest``. The velocity of the particle is then added to the position
    of the particle.

    Shi and Eberhart [2]_ describe using an inertial weight, or a friction
    parameter, to balance the effect of the global and local search. This acts
    as a limiting factor to ensure velocity does not increase, or decrease,
    unbounded.

    **Constrained Optimization**

    The standard PSO algorithm does not guarantee that the individual solutions
    will converge to a feasible global solution. To solve this, Lorem and Ipsum
    [3]_ suggested an approach where each particle selects another particle,
    called the leader and uses this particle's ``pbest`` value, instead of its
    own, to update its velocity. The leader for a given particle is selected by
    picking the particle whose ``pbest`` is closest to the current position of
    the given particle. Further, ``pbest`` is updated only those particles
    where the sum of the constraint vector is less than the constraint
    tolerance.

    References
    ----------
    .. [1] Eberhart, R. and Kennedy, J., 1995, October. A new optimizer
        using particle swarm theory. In Micro Machine and Human Science, 1995.
        MHS'95., Proceedings of the Sixth International Symposium on (pp.
        39-43). IEEE.
    .. [2] Shi, Y. and Eberhart, R., 1998, May. A modified particle swarm
        optimizer. In Evolutionary Computation Proceedings, 1998. IEEE World
        Congress on Computational Intelligence., The 1998 IEEE International
        Conference on (pp. 69-73). IEEE.
    .. [3] Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer
        volutpat feugiat imperdiet. Phasellus placerat elit nec erat tristique
        faucibus. Suspendisse at nunc odio. Nullam sagittis nunc ut sed.

    Examples
    --------
    Let us consider the problem of minimizing the Rosenbrock function,
    implemented as ``scipy.optimize.rosen``.

    >>> import numpy as np
    >>> from psopy import minimize_pso
    >>> from scipy.optimize import rosen

    Initialize 1000 particles and run the minimization function:

    >>> x0 = np.random.uniform(0, 2, (1000, 5))
    >>> res = minimize_pso(rosen, x0, options={'stable_iter': 50})
    >>> res.x
    array([1.00000003, 1.00000017, 1.00000034, 1.0000006 , 1.00000135])

    Next, we consider a minimization problem with several constraints. The
    objective function is:

    >>> fun = lambda x: (x[0] - 1)**2 + (x[1] - 2.5)**2

    The constraints defined as:

    >>> cons = ({'type': 'ineq', 'fun': lambda x:  x[0] - 2 * x[1] + 2},
    ...         {'type': 'ineq', 'fun': lambda x: -x[0] - 2 * x[1] + 6},
    ...         {'type': 'ineq', 'fun': lambda x: -x[0] + 2 * x[1] + 2},
    ...         {'type': 'ineq', 'fun': lambda x: x[0]},
    ...         {'type': 'ineq', 'fun': lambda x: x[1]})

    The intial positions for constrained optimization must adhere to the
    constraints imposed by the problem. This can be ensured using the provided
    function ``psopy.init_feasible``. Note, there are several caveats regarding
    the use of this function. Consult its documentation for more information.

    >>> from psopy import init_feasible
    >>> x0 = init_feasible(cons, low=0., high=2., shape=(1000, 2))

    Running the constrained version of the function:

    >>> res = minimize_pso(fun, x0, constrainsts=cons, options={
    ...     'g_rate': 1., 'l_rate': 1., 'max_velocity': 4., 'stable_iter': 50})
    >>> res.x
    array([ 1.39985398,  1.69992748])

    """
    x0 = np.asarray(x0)
    if x0.dtype.kind in np.typecodes["AllInteger"]:
        x0 = np.asarray(x0, dtype=float)

    if not isinstance(args, tuple):
        args = (args,)

    if not options:
        options = {}

    conargs = {}
    if tol is not None:
        options.setdefault('ptol', tol)
        options.setdefault('ctol', tol)
        conargs['sttol'] = options.pop('sttol', tol)
        conargs['eqtol'] = options.pop('eqtol', tol)

    fun_ = ft.update_wrapper(
        lambda x: np.apply_along_axis(fun, 1, x, *args), fun)

    if callback is not None:
        options['callback'] = ft.update_wrapper(
            lambda x: np.apply_along_axis(callback, 1, x), callback)

    if constraints:
        options['confunc'] = gen_confunc(constraints, **conargs)

    return pswarmopt(fun_, x0, **options)
