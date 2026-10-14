// This file is part of the uutils coreutils package.
//
// For the full copyright and license information, please view the LICENSE
// file that was distributed with this source code.

// spell-checker:ignore (ToDO) libstdbuf

use std::env;

fn main() {
    // do not compile libstdbuf for windows target. The windows stdbuf.exe loads libstdbuf.dll compiled for the cygwin target.
    if env::var("CARGO_CFG_UNIX").is_err() {
        return;
    }
    // Keep the standalone preload library independent of ARM libc's EHABI
    // exports, just like the utilities which link uucore.
    if env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("ohos")
        && env::var("CARGO_CFG_TARGET_ARCH").as_deref() == Ok("arm")
    {
        println!("cargo:rerun-if-env-changed=OHOS_NDK_HOME");
        let sdk = std::path::PathBuf::from(
            env::var_os("OHOS_NDK_HOME")
                .expect("set OHOS_NDK_HOME to the SDK root containing native/ for ARM OHOS builds"),
        );
        let library = sdk.join("native/llvm/lib/arm-linux-ohos");
        assert!(
            library.join("libunwind.a").is_file(),
            "ARM OHOS requires the SDK's LLVM libunwind.a"
        );
        println!("cargo:rustc-link-search=native={}", library.display());
        println!("cargo:rustc-link-lib=static:+whole-archive=unwind");
    }
    // Make sure we're building position-independent code for use with LD_PRELOAD
    println!("cargo:rustc-link-arg=-fPIC");

    let target = env::var("TARGET").unwrap_or_else(|_| "unknown".to_string());
    // Ensure the library doesn't have any undefined symbols (-z flag not supported on macOS and Cygwin)
    if !target.contains("apple-darwin") && !target.contains("cygwin") {
        println!("cargo:rustc-link-arg=-z");
        println!("cargo:rustc-link-arg=defs");
    }

    println!("cargo:rerun-if-changed=src/libstdbuf.rs");
}
