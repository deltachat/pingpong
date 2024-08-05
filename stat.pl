#!/usr/bin/env perl
use v5.30;
use strict;
use warnings;

my $file = $ARGV[0] or die "Missing command line argument\n";
open(my $data, '<', $file) or die "Could not open '$file'\n";
my $prev;
my @values = ();
while (my $line = <$data>) {
  chomp $line;
  my @fields = split "," , $line;
  if (defined $prev) {
     push(@values, $fields[1])
  }
  $prev = $fields[1]
}
@values = sort @values;
say "min:    " . ($values[0]);
say "p05:    " . ($values[int($#values * 5 / 100)]);
say "median: " . ($values[int($#values / 2)]);
say "p95:    " . ($values[int($#values * 95 / 100)]);
say "max:    " . ($values[-1]);
