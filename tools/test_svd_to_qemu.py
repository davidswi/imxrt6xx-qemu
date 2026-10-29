#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from io import StringIO
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(Path(__file__).parent))

import svd_to_qemu


SVD = """\
<?xml version="1.0" encoding="utf-8"?>
<device schemaVersion="1.1" xmlns:xs="http://www.w3.org/2001/XMLSchema-instance">
  <name>TestChip</name>
  <version>1</version>
  <description>Generator fixture</description>
  <addressUnitBits>8</addressUnitBits>
  <width>32</width>
  <size>32</size>
  <access>read-write</access>
  <resetValue>0</resetValue>
  <resetMask>0xffffffff</resetMask>
  <peripherals>
    <peripheral>
      <name>TIMER0</name>
      <groupName>TIMER</groupName>
      <baseAddress>0x40000000</baseAddress>
      <addressBlock><offset>0</offset><size>0x20</size><usage>registers</usage></addressBlock>
      <interrupt><name>TIMER0</name><value>7</value></interrupt>
      <registers>
        <register>
          <name>CTRL</name><addressOffset>0</addressOffset><resetValue>1</resetValue>
          <fields>
            <field><name>ENABLE</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
            <field><name>BUSY</name><bitOffset>1</bitOffset><bitWidth>1</bitWidth><access>read-only</access></field>
          </fields>
        </register>
        <register>
          <name>STATUS</name><addressOffset>4</addressOffset><access>read-write</access>
          <modifiedWriteValues>oneToClear</modifiedWriteValues>
          <resetMask>0xff</resetMask>
        </register>
        <register>
          <name>RESULT</name><addressOffset>8</addressOffset><access>read-only</access>
        </register>
        <register>
          <name>INPUT</name><addressOffset>8</addressOffset><access>write-only</access>
        </register>
        <register>
          <dim>2</dim><dimIncrement>4</dimIncrement><dimIndex>0-1</dimIndex>
          <name>MATCH[%s]</name><addressOffset>0x10</addressOffset><resetMask>0xffff</resetMask>
        </register>
      </registers>
    </peripheral>
    <peripheral derivedFrom="TIMER0">
      <name>TIMER1</name><groupName>TIMER</groupName><baseAddress>0x40001000</baseAddress>
      <interrupt><name>TIMER1</name><value>8</value></interrupt>
    </peripheral>
  </peripherals>
</device>
"""


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.svd = Path(self.directory.name) / "test.svd"
        self.svd.write_text(textwrap.dedent(SVD), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_group_generates_reusable_model(self):
        output = StringIO()
        result = svd_to_qemu.main(
            ["--svd", str(self.svd), "--peripheral", "TIMER"], output
        )
        source = output.getvalue()

        self.assertEqual(result, 0)
        self.assertIn('#define TYPE_TIMER "timer"', source)
        self.assertIn("TIMER0: base=0x40000000, IRQs=TIMER0=7", source)
        self.assertIn("TIMER1: base=0x40001000, IRQs=TIMER1=8", source)
        self.assertIn("UINT64_C(0x0000000000000003)", source)  # CTRL read mask
        self.assertIn("UINT64_C(0x0000000000000001) }, /* CTRL */", source)
        self.assertIn("SVD_WRITE_ONE_TO_CLEAR", source)
        self.assertIn("/* INPUT / RESULT */", source)
        self.assertIn("/* MATCH[0] */", source)
        self.assertIn("/* MATCH[1] */", source)

    def test_exact_instance_only_lists_that_instance(self):
        args = svd_to_qemu.build_parser().parse_args(
            ["--svd", str(self.svd), "--peripheral", "TIMER1"]
        )
        source = svd_to_qemu.generate(args)

        self.assertIn("TIMER1: base=0x40001000", source)
        self.assertNotIn("TIMER0: base=", source)
        self.assertIn('#define TYPE_TIMER1 "timer1"', source)


if __name__ == "__main__":
    unittest.main()
