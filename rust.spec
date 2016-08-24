# The channel can be stable, beta, or nightly
%{!?channel: %global channel stable}

# To bootstrap from scratch, set the channel and date from src/stage0.txt
# e.g. 1.10.0 wants rustc: 1.9.0-2016-05-24
# or nightly wants some beta-YYYY-MM-DD
%bcond_with bootstrap
%global bootstrap_channel 1.10.0
%global bootstrap_date 2016-07-05

# Use "rebuild" when building with a distro rustc of the same version.
# Turn this off when the distro has the prior release, matching bootstrap.
# Note, 1.12 will be able to autodetect this via PR34779.
%bcond_with rebuild

# The script for minidebuginfo copies symbols and *notes* into a "mini"
# ELF object compressed into the .gnu_debugdata section.  This includes our
# relatively large .note.rustc metadata, bloating every library.  Eventually
# that metadata should be stripped beforehand -- see rust #23366 and #26764.
# Note, 1.12 will move to unallocated data via PR35409, then can be stripped.
%undefine _include_minidebuginfo

Name:           rust
Version:        1.11.0
Release:        1%{?dist}
Summary:        The Rust Programming Language
License:        (ASL 2.0 or MIT) and (BSD and ISC and MIT)
# ^ written as: (rust itself) and (bundled libraries)
URL:            https://www.rust-lang.org

%if "%{channel}" == "stable"
%global rustc_package rustc-%{version}
%else
%global rustc_package rustc-%{channel}
%endif
Source0:        https://static.rust-lang.org/dist/%{rustc_package}-src.tar.gz

%if %with bootstrap
%global bootstrap_base https://static.rust-lang.org/dist/%{bootstrap_date}/rustc-%{bootstrap_channel}
Source1:        %{bootstrap_base}-x86_64-unknown-linux-gnu.tar.gz
Source2:        %{bootstrap_base}-i686-unknown-linux-gnu.tar.gz
#Source3:        %{bootstrap_base}-armv7-unknown-linux-gnueabihf.tar.gz
#Source4:        %{bootstrap_base}-aarch64-unknown-linux-gnu.tar.gz
%endif

# Only x86_64 and i686 are Tier 1 platforms at this time.
# https://doc.rust-lang.org/stable/book/getting-started.html#tier-1
ExclusiveArch:  x86_64 i686
#ExclusiveArch:  x86_64 i686 armv7hl aarch64
%ifarch armv7hl
%global rust_triple armv7-unknown-linux-gnueabihf
%else
%global rust_triple %{_target_cpu}-unknown-linux-gnu
%endif

Patch1:         rust-1.11.0-no-bootstrap-download.patch

BuildRequires:  make
BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  llvm-devel
BuildRequires:  zlib-devel
BuildRequires:  python2
BuildRequires:  curl

%if %without bootstrap
%if %with rebuild
BuildRequires:  %{name} < %{version}-%{release}
BuildRequires:  %{name} >= %{version}
%else
BuildRequires:  %{name} < %{version}
BuildRequires:  %{name} >= %{bootstrap_channel}
%endif
%endif

# make check: src/test/run-pass/wait-forked-but-failed-child.rs
BuildRequires:  /usr/bin/ps

# Rust started using cmake for its bundled compiler-rt, but this requires
# llvm-static to be installed.  But then llvm-config starts printing flags
# for static linkage, with no way to force it shared.
#
# For now, we'll bypass all that and just use the distro build.  Then in the
# next release, Rust is moving toward a true fork of these builtins, with the
# eventual goal of rewriting them in Rust proper.
BuildRequires:  compiler-rt
Provides:       bundled(compiler-rt) = 3.8
%global clang_builtins %{_libdir}/clang/3.8.0/lib/libclang_rt.builtins-%{_target_cpu}.a

# TODO: work on unbundling these!
Provides:       bundled(hoedown) = 3.0.5
Provides:       bundled(jquery) = 2.1.4
Provides:       bundled(libbacktrace) = 6.1.0
Provides:       bundled(miniz) = 1.14

# The C compiler is needed at runtime just for linking.  Someday rustc might
# invoke the linker directly, and then we'll only need binutils.
# https://github.com/rust-lang/rust/issues/11937
Requires:       gcc

# ALL Rust libraries are private, because they don't keep an ABI.
%global _privatelibs lib.*-[[:xdigit:]]{8}[.]so.*
%global __provides_exclude ^(%{_privatelibs})$
%global __requires_exclude ^(%{_privatelibs})$

%description
Rust is a systems programming language that runs blazingly fast, prevents
segfaults, and guarantees thread safety.

This package includes the Rust compiler, standard library, and documentation
generator.


%package gdb
Summary:        GDB pretty printers for Rust
BuildArch:      noarch
Requires:       gdb

%description gdb
This package includes the rust-gdb script, which allows easier debugging of Rust
programs.


%package doc
Summary:        Documentation for Rust
# NOT BuildArch:      noarch
# Note, while docs are mostly noarch, some things do vary by target_arch.
# Koji will fail the build in rpmdiff if two architectures build a noarch
# subpackage differently, so instead we have to keep its arch.

%description doc
This package includes HTML documentation for the Rust programming language and
its standard library.


# TODO: consider a rust-std package containing .../rustlib/$target
# This might allow multilib cross-compilation to work naturally.


%prep
%setup -q -n %{rustc_package}

%patch1 -p1 -b .no-download

# unbundle
rm -rf src/llvm/ src/jemalloc/
rm -rf src/compiler-rt/

# extract bundled licenses for packaging
cp src/rt/hoedown/LICENSE src/rt/hoedown/LICENSE-hoedown
sed -e '/*\//q' src/libbacktrace/backtrace.h \
  >src/libbacktrace/LICENSE-libbacktrace

# rust-gdb has hardcoded SYSROOT/lib -- let's make it noarch
sed -i.noarch -e 's#DIRECTORY=".*"#DIRECTORY="%{_datadir}/%{name}/etc"#' \
  src/etc/rust-gdb

# These tests assume that alloc_jemalloc is present
sed -i.jemalloc -e '1i // ignore-test jemalloc is disabled' \
  src/test/compile-fail/allocator-dylib-is-system.rs \
  src/test/compile-fail/allocator-rust-dylib-is-jemalloc.rs \
  src/test/run-pass/allocator-default.rs

# Fedora's LLVM doesn't support any mips targets -- see "llc -version"
sed -i.nomips -e '/target=mips/,+1s/^/# unsupported /' \
  src/test/run-make/atomic-lock-free/Makefile

%if %without bootstrap
# The hardcoded stage0 "lib" is inappropriate when using Fedora's own rustc
sed -i.libdir -e '/^HLIB_RELATIVE/s/lib$/$$(CFG_LIBDIR_RELATIVE)/' mk/main.mk
%endif

%if %with bootstrap
mkdir -p dl/
cp -t dl/ %{SOURCE1} %{SOURCE2} # %{SOURCE3} %{SOURCE4}
%endif


%build
%configure --disable-option-checking \
  --build=%{rust_triple} --host=%{rust_triple} --target=%{rust_triple} \
  %{!?with_bootstrap:--enable-local-rust --local-rust-root=%{_prefix} %{?with_rebuild:--enable-local-rebuild}} \
  --llvm-root=%{_prefix} --disable-codegen-tests \
  --disable-jemalloc \
  --disable-rpath \
  --enable-debuginfo \
  --release-channel=%{channel}

# Bypass the compiler-rt build -- see above.
cp %{clang_builtins} ./%{rust_triple}/rt/libcompiler-rt.a

%make_build VERBOSE=1


%install
%make_install VERBOSE=1

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}/%{_libdir}/rustlib/ -maxdepth 1 -type f -exec rm -v '{}' '+'

# We don't want to ship the target shared libraries for lack of any Rust ABI.
find %{buildroot}/%{_libdir}/rustlib/ -type f -name '*.so' -exec rm -v '{}' '+'

# The remaining shared libraries should be executable for debuginfo extraction.
find %{buildroot}/%{_libdir}/ -type f -name '*.so' -exec chmod -v +x '{}' '+'

# FIXME: __os_install_post will strip the rlibs
# -- should we find a way to preserve debuginfo?

# Remove unwanted documentation files (we already package them)
rm -f %{buildroot}/%{_docdir}/%{name}/README.md
rm -f %{buildroot}/%{_docdir}/%{name}/COPYRIGHT
rm -f %{buildroot}/%{_docdir}/%{name}/LICENSE-APACHE
rm -f %{buildroot}/%{_docdir}/%{name}/LICENSE-MIT

# Sanitize the HTML documentation
find %{buildroot}/%{_docdir}/%{name}/html -empty -delete
find %{buildroot}/%{_docdir}/%{name}/html -type f -exec chmod -v -x '{}' '+'

# Move rust-gdb's python scripts so they're noarch
mkdir -p %{buildroot}/%{_datadir}/%{name}
mv -v %{buildroot}/%{_libdir}/rustlib/etc %{buildroot}/%{_datadir}/%{name}/


%check
# Note, many of the tests execute in parallel threads,
# so it's better not to use a parallel make here.
# The results are not stable on koji, so mask errors and just log it.
make check-lite VERBOSE=1 -k || echo "make check-lite exited with code $?"


%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig


%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%license src/libbacktrace/LICENSE-libbacktrace
%license src/rt/hoedown/LICENSE-hoedown
%doc README.md
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_mandir}/man1/rustc.1*
%{_mandir}/man1/rustdoc.1*
%{_libdir}/lib*
%dir %{_libdir}/rustlib
%{_libdir}/rustlib/%{rust_triple}


%files gdb
%{_bindir}/rust-gdb
%{_datadir}/%{name}


%files doc
%dir %{_docdir}/%{name}
%license %{_docdir}/%{name}/html/FiraSans-LICENSE.txt
%license %{_docdir}/%{name}/html/Heuristica-LICENSE.txt
%license %{_docdir}/%{name}/html/LICENSE-APACHE.txt
%license %{_docdir}/%{name}/html/LICENSE-MIT.txt
%license %{_docdir}/%{name}/html/SourceCodePro-LICENSE.txt
%license %{_docdir}/%{name}/html/SourceSerifPro-LICENSE.txt
%doc %{_docdir}/%{name}/html/


%changelog
* Wed Aug 24 2016 Josh Stone <jistone@redhat.com> - 1.11.0-1
- Update to 1.11.0.
- Drop the backported patches.
- Patch get-stage0.py to trust existing bootstrap binaries.
- Use libclang_rt.builtins from compiler-rt, dodging llvm-static issues.
- Use --local-rust-root to make sure the right bootstrap is used.

* Sat Aug 13 2016 Josh Stone <jistone@redhat.com> 1.10.0-4
- Rebuild without bootstrap binaries.

* Fri Aug 12 2016 Josh Stone <jistone@redhat.com> - 1.10.0-3
- Initial import into Fedora (#1356907), bootstrapped
- Format license text as suggested in review.
- Note how the tests already run in parallel.
- Undefine _include_minidebuginfo, because it duplicates ".note.rustc".
- Don't let checks fail the whole build.
- Note that -doc can't be noarch, as rpmdiff doesn't allow variations.

* Tue Jul 26 2016 Josh Stone <jistone@redhat.com> - 1.10.0-2
- Update -doc directory ownership, and mark its licenses.
- Package and declare licenses for libbacktrace and hoedown.
- Set bootstrap_base as a global.
- Explicitly require python2.

* Thu Jul 14 2016 Josh Stone <jistone@fedoraproject.org> - 1.10.0-1
- Initial package, bootstrapped
