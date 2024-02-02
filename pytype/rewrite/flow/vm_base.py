"""Base implementation of an abstract virtual machine for bytecode.

This module contains a VmBase class, which provides a base implementation of a
VM that analyzes bytecode one instruction (i.e., opcode) at a time, tracking
variables and conditions. Use VmBase by subclassing it and adding a
byte_{opcode_name} method implementing each opcode.
"""

import dataclasses
from typing import Dict

from pytype.blocks import blocks
from pytype.rewrite.flow import state
from pytype.rewrite.flow import variables


@dataclasses.dataclass
class _Step:
  """Block and opcode indices for a VM step."""

  block: int
  opcode: int


class VmConsumedError(Exception):
  """Raised when step() is called on a VM with no more opcodes to execute."""


class VmBase:
  """Virtual machine."""

  def __init__(
      self, code: blocks.OrderedCode,
      initial_locals: Dict[str, variables.Variable],
  ):
    # Sanity check: non-empty code
    assert code.order and all(block.code for block in code.order)
    self._code = code  # bytecode
    self._initial_locals = initial_locals  # locally scoped names before VM runs
    self._current_step = _Step(0, 0)  # current block and opcode indices

    self._states: Dict[int, state.BlockState] = {}  # block id to state
    # Initialize the state of the first block.
    self._states[self._code.order[0].id] = state.BlockState(
        locals_=dict(self._initial_locals))
    self._current_state: state.BlockState = None  # state of the current block

  def step(self) -> None:
    """Runs one opcode."""
    # Grab the current block and opcode.
    block_index = self._current_step.block
    if block_index == -1:
      raise VmConsumedError()
    opcode_index = self._current_step.opcode
    block = self._code.order[block_index]
    opcode = block[opcode_index]
    # Grab the block's initial state.
    self._current_state = self._states[block.id]
    # Run the opcode.
    opname = opcode.__class__.__name__
    try:
      op_impl = getattr(self, f'byte_{opname}')
    except AttributeError as e:
      raise NotImplementedError(f'Opcode {opname} not implemented') from e
    op_impl(opcode)
    # Update current block and opcode.
    if opcode is not block[-1]:
      self._current_step.opcode += 1
      return
    if opcode.carry_on_to_next() and not opcode.has_known_jump():
      # Merge the current state into the next.
      self._merge_state_into(self._current_state, opcode.next.index)
    if block is self._code.order[-1]:
      self._current_step.block = -1
    else:
      self._current_step.block += 1
      self._current_step.opcode = 0

  def _merge_state_into(
      self, from_state: state.BlockState, block_id: int) -> None:
    self._states[block_id] = from_state.merge_into(self._states.get(block_id))
