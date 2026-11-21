// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract Groth16Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 2439870853374664008519987343619396285392140768890518893756817665763378589214;
    uint256 constant alphay  = 7256068733757625801626169603164067715156451908457919083030184027279288856617;
    uint256 constant betax1  = 13251612346605095728704248957489111581617603552297381400566228570379626476420;
    uint256 constant betax2  = 21121961155776844228838451722195336583243165677574409809036078325658456640641;
    uint256 constant betay1  = 2811734423277722491683819709823921527172030915453126845960072948617149772799;
    uint256 constant betay2  = 1668583213223862276577319798207382618859269811791482182829281066747708065720;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 16220171589476943104359394417440104095700400170132638327872135320455903262110;
    uint256 constant deltax2 = 12739385691078776293122056277747633974850279928908695113067623587103196417389;
    uint256 constant deltay1 = 6929287046965992187419620666737972835213960239756487997540808959659979560347;
    uint256 constant deltay2 = 18173954347438952924560587542781492168621702076075655540488196465162420119156;

    
    uint256 constant IC0x = 16268962049930869780457474370059293033922643299786042256062244266739443947583;
    uint256 constant IC0y = 12694404374578874081520206912617605341883007281063932988708791788930981379769;
    
    uint256 constant IC1x = 11845554948936655132410853397905736858607897184819896341644133974696018069373;
    uint256 constant IC1y = 9535508297816277616339912956760302946062771426093583412596013601231888694961;
    
    uint256 constant IC2x = 4162377342076046109731519479359554833698222814295004941435851192437572287006;
    uint256 constant IC2y = 7988572731504682959903082394550788322646100477170649887142799081850166806362;
    
    uint256 constant IC3x = 274423501509276336393725397768758992753274459435947153429380000700282978167;
    uint256 constant IC3y = 3477885217098548916205999985059676429885030899418424955794792011357303813509;
    
    uint256 constant IC4x = 15586201351001493321314401735507121674799891731921248091961178200632565669067;
    uint256 constant IC4y = 18156986323810921021740704273019950553735607743590513540266525160257224717774;
    
    uint256 constant IC5x = 14691242466543629083280866881822572821193879702769285655772769134089999025257;
    uint256 constant IC5y = 4135091516318420291387092101875826532628418769020118387859729296728650511805;
    
    uint256 constant IC6x = 3743006152312222204819608878496183939801143099543061982713820680943314846292;
    uint256 constant IC6y = 1384048882599350837544928788372527448719407729942216274920807791957331215722;
    
    uint256 constant IC7x = 18617851715021542663704168644987054593301276803784770429008399043301376748613;
    uint256 constant IC7y = 17174447669964307438132775728379782371263680818439506586512789399863954478107;
    
    uint256 constant IC8x = 15183003736161825887251616479486448331519215853200212513712631327416863070620;
    uint256 constant IC8y = 17827344932487579056404968852771285214199948335533019587254799872530282073921;
    
    uint256 constant IC9x = 15776676718728183169564962571087734616949477955189472975846452438574544266774;
    uint256 constant IC9y = 5960506756600311806831909196760961116001469340368240974639429882529140196248;
    
    uint256 constant IC10x = 8627763903949569404640077691810052536693576435487837848195513754333718306467;
    uint256 constant IC10y = 14422048252506855688572279326838696616758323407499396840946074016451171501504;
    
    uint256 constant IC11x = 21179742926716400225551992817247425473343352423980067730870646145105466421529;
    uint256 constant IC11y = 21131654361420100176791148205239660776373937664234199110732223427699272325094;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[11] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
